"""The Kerbl IoT integration.

This module currently only wires up the (still empty) platform list so the
integration is structurally complete, importable, and testable from the
first commit onward. The Kerbl account client, the push-driven
``DataUpdateCoordinator`` and the entity platforms described in the project
plan are added in later build-out steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS


@dataclass
class KerblIotRuntimeData:
    """Runtime data attached to a Kerbl IoT config entry.

    Will grow to hold the authenticated ``KerblIOTApi``/``KerblIOT`` client
    and the account-level ``DataUpdateCoordinator`` once the config flow and
    coordinator are implemented.
    """


type KerblIotConfigEntry = ConfigEntry[KerblIotRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Set up Kerbl IoT from a config entry."""
    entry.runtime_data = KerblIotRuntimeData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Unload a Kerbl IoT config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
