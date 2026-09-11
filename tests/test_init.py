"""Tests for setting up and unloading a Kerbl IoT config entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kerbl_iot.const import DOMAIN


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """The scaffold (still without platforms) sets up and unloads cleanly.

    This exercises the whole async_setup_entry / async_unload_entry
    round-trip end to end so later steps can build on a proven harness.
    """
    entry = MockConfigEntry(domain=DOMAIN, title="Kerbl IoT (test@example.com)")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
