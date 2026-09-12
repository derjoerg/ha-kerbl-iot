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
        mock_load.assert_awaited_once()

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
