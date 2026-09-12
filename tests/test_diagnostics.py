"""Tests for the Kerbl IoT diagnostics platform.

Calls ``async_get_config_entry_diagnostics`` / ``async_get_device_diagnostics``
directly rather than through the diagnostics integration's HTTP/websocket
download flow: that flow only adds JSON (de)serialization and a registered
platform lookup on top, neither of which is this integration's own logic to
test. Uses the same ``FakeApi`` transport double as test_coordinator.py and
test_entities.py, so no real socket is ever touched (see those modules'
docstrings for why that matters on this project).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kerbl_iot.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.kerbl_iot.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from tests.kerbl_fakes import SMART_COOP_ID, FakeApi, smart_coop_payload

ENTRY_DATA = {
    "email": "farmer@example.com",
    "access_token": "access-123",
    CONF_REFRESH_TOKEN: "refresh-456",
}


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[FakeApi, MockConfigEntry]]:
    """Set up one config entry against a fresh FakeApi and unload it after.

    Mirrors tests/test_entities.py's fixture of the same name and for the
    same reason: ``async_setup_entry`` constructs ``KerblIOTApi`` itself, so
    the class (not an instance) is patched to hand back this fixture's
    ``api`` regardless of what it's constructed with.
    """
    api = FakeApi([smart_coop_payload()])

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kerbl_iot.KerblIOTApi",
        MagicMock(return_value=api),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        yield api, entry

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


def _smart_coop_device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    """Look up the device registry entry for the test SmartCoop.

    Uses ``async_entries_for_config_entry`` rather than the newer
    identifier-lookup helpers, since it's been a stable part of the device
    registry API for the whole version range this integration supports.
    """
    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    device = next(
        (d for d in devices if (DOMAIN, SMART_COOP_ID) in d.identifiers), None
    )
    assert device is not None, "SmartCoop device was not registered"
    return device


async def test_config_entry_diagnostics_redacts_account_identifiers(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Email, tokens, title and unique_id never appear in the output."""
    _api, entry = setup_entry

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["title"] == REDACTED
    assert diagnostics["entry"]["unique_id"] == REDACTED
    assert diagnostics["entry"]["data"]["email"] == REDACTED
    assert diagnostics["entry"]["data"]["access_token"] == REDACTED
    assert diagnostics["entry"]["data"][CONF_REFRESH_TOKEN] == REDACTED
    # Nothing in the whole payload leaks the raw e-mail address as a
    # substring either (e.g. hidden inside some other untouched field).
    assert "farmer@example.com" not in repr(diagnostics)


async def test_config_entry_diagnostics_reports_coordinator_health(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Coordinator health surfaces independent of any one SmartCoop."""
    _api, entry = setup_entry

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["last_exception"] is None
    assert diagnostics["coordinator"]["update_interval_seconds"] == pytest.approx(
        17 * 60
    )


async def test_config_entry_diagnostics_includes_smart_coop_state(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Kerbl device state is present, redacted, and enriched with availability."""
    _api, entry = setup_entry

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["kerbl"]["websocket_connected"] is True
    smart_coops = diagnostics["kerbl"]["smart_coops"]
    assert len(smart_coops) == 1
    smart_coop_data = smart_coops[0]
    assert smart_coop_data["id"] == SMART_COOP_ID
    assert smart_coop_data["user_id"] == REDACTED
    assert smart_coop_data["available"] is True
    assert smart_coop_data["door"]["state"] == "OPEN"


async def test_device_diagnostics_includes_logs_and_availability(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """A device-level download returns that one SmartCoop's state and logs."""
    _api, entry = setup_entry
    device = _smart_coop_device(hass, entry)

    diagnostics = await async_get_device_diagnostics(hass, entry, device)

    assert diagnostics["id"] == SMART_COOP_ID
    assert diagnostics["user_id"] == REDACTED
    assert diagnostics["available"] is True
    assert diagnostics["logs"] == []


async def test_device_diagnostics_unknown_device_reports_an_error(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """A device with no matching SmartCoop fails gracefully, not with a KeyError."""
    _api, entry = setup_entry
    registry = dr.async_get(hass)
    unrelated_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "not-a-real-smart-coop")},
    )

    diagnostics = await async_get_device_diagnostics(hass, entry, unrelated_device)

    assert "error" in diagnostics
