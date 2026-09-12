"""The Kerbl IoT integration.

Sets up a Kerbl account (one config entry per account) by restoring its
stored tokens onto a ``KerblIOTApi`` client and confirming the session is
still valid via one authenticated call. A push-driven
``DataUpdateCoordinator`` built around the resulting ``KerblIOT`` wrapper,
and the entity platforms themselves, are added in later build-out steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from kerbl_iot import (
    KerblAuthenticationError,
    KerblConnectionError,
    KerblIOT,
    KerblIOTApi,
    KerblProtocolError,
)

from .const import CONF_REFRESH_TOKEN, PLATFORMS

# The client is reconstructed from stored tokens via restore_tokens(), so the
# password is never needed (and never available) again after the config
# flow. login() -- the only place the client uses it -- is never called on
# this instance; the placeholder is kept only to satisfy the constructor.
_UNUSED_PASSWORD_PLACEHOLDER = ""


@dataclass
class KerblIotRuntimeData:
    """Runtime data attached to a Kerbl IoT config entry."""

    kerbl: KerblIOT


KerblIotConfigEntry: TypeAlias = ConfigEntry[KerblIotRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Set up Kerbl IoT from a config entry."""
    api = KerblIOTApi(
        email=entry.data[CONF_EMAIL], password=_UNUSED_PASSWORD_PLACEHOLDER
    )
    api.restore_tokens(entry.data[CONF_ACCESS_TOKEN], entry.data[CONF_REFRESH_TOKEN])
    kerbl = KerblIOT(api)

    try:
        # Loads the account's SmartCoops, which both confirms the restored
        # tokens are still valid and gives the coordinator (added next) a
        # populated KerblIOT to start from.
        await kerbl.load()
    except KerblAuthenticationError as err:
        await kerbl.async_close()
        raise ConfigEntryAuthFailed(
            "Kerbl IoT session expired; reauthentication required."
        ) from err
    except (KerblConnectionError, KerblProtocolError) as err:
        await kerbl.async_close()
        raise ConfigEntryNotReady(
            "Kerbl IoT service is currently unreachable."
        ) from err

    entry.runtime_data = KerblIotRuntimeData(kerbl=kerbl)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Unload a Kerbl IoT config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.kerbl.async_close()
    return unload_ok
