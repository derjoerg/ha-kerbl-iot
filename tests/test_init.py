"""Tests for setting up and unloading a Kerbl IoT config entry."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kerbl_iot.const import CONF_REFRESH_TOKEN, DOMAIN
from kerbl_iot import KerblAuthenticationError, KerblConnectionError

ENTRY_DATA = {
    "email": "farmer@example.com",
    "access_token": "access-123",
    CONF_REFRESH_TOKEN: "refresh-456",
}


def _mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
    )


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """A restorable session sets up and unloads cleanly end to end."""
    entry = _mock_entry()
    entry.add_to_hass(hass)

    with (
        patch("kerbl_iot.KerblIOT.load", AsyncMock(return_value=None)) as mock_load,
        patch(
            "kerbl_iot.KerblIOT.async_close", AsyncMock(return_value=None)
        ) as mock_close,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        # load() runs three times here only because this mock is a pure
        # no-op and never actually populates KerblIOT._smart_coops: the
        # coordinator's own explicit load (for auth/connection error
        # handling), KerblIOT.connect_websocket()'s "load if I don't have
        # any devices yet" guard (which keeps re-triggering since the
        # mocked load never satisfies it), and the coordinator's first
        # regular _async_update_data() poll. A real load populates the
        # SmartCoop list, so connect_websocket()'s guard fires at most
        # once -- two real HTTP requests per setup in production, not three.
        assert mock_load.await_count == 3

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        mock_close.assert_awaited_once()


async def test_setup_starts_reauth_on_authentication_error(hass: HomeAssistant) -> None:
    """An expired/invalid stored session triggers Home Assistant's reauth flow."""
    entry = _mock_entry()
    entry.add_to_hass(hass)

    with patch(
        "kerbl_iot.KerblIOT.load",
        AsyncMock(side_effect=KerblAuthenticationError("expired")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(
        flow["handler"] == DOMAIN and flow["context"]["source"] == SOURCE_REAUTH
        for flow in flows
    )


async def test_setup_retries_on_connection_error(hass: HomeAssistant) -> None:
    """A transient connection problem schedules a setup retry, not reauth."""
    entry = _mock_entry()
    entry.add_to_hass(hass)

    with patch(
        "kerbl_iot.KerblIOT.load",
        AsyncMock(side_effect=KerblConnectionError("unreachable")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
