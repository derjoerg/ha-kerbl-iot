"""The Kerbl IoT integration.

Sets up a Kerbl account (one config entry per account) by restoring its
stored tokens onto a ``KerblIOTApi`` client and handing the resulting
``KerblIOT`` wrapper to a ``KerblIotDataUpdateCoordinator`` (see
``coordinator.py``), which keeps its SmartCoop devices current -- primarily
via Socket.IO push updates, with a polling fallback -- for the entity
platforms added in later build-out steps.
"""

from __future__ import annotations

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from kerbl_iot import KerblIOT, KerblIOTApi

from .const import CONF_REFRESH_TOKEN, PLATFORMS
from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator

# The client is reconstructed from stored tokens via restore_tokens(), so the
# password is never needed (and never available) again after the config
# flow. login() -- the only place the client uses it -- is never called on
# this instance; the placeholder is kept only to satisfy the constructor.
_UNUSED_PASSWORD_PLACEHOLDER = ""


async def async_setup_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Set up Kerbl IoT from a config entry."""
    # Home Assistant's shared aiohttp session, not a dedicated one: since
    # kerbl-iot 0.1.7 the bearer token is sent as a per-request header
    # instead of being written onto the session's default headers, so
    # multiple accounts (config entries) can safely share one session
    # without one login's token leaking onto another account's requests.
    # KerblIOTApi never closes a session it didn't create itself, so this
    # shared session is left open for the rest of Home Assistant on unload.
    session = async_get_clientsession(hass)
    api = KerblIOTApi(
        email=entry.data[CONF_EMAIL],
        password=_UNUSED_PASSWORD_PLACEHOLDER,
        session=session,
    )
    api.restore_tokens(entry.data[CONF_ACCESS_TOKEN], entry.data[CONF_REFRESH_TOKEN])
    kerbl = KerblIOT(api)

    # Loading, translating auth/connection errors into the
    # ConfigEntryAuthFailed / ConfigEntryNotReady Home Assistant expects from
    # a first refresh, and opening the Socket.IO push channel all happen
    # inside the coordinator itself (KerblIotDataUpdateCoordinator._async_setup).
    coordinator = KerblIotDataUpdateCoordinator(hass, entry, kerbl)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KerblIotConfigEntry) -> bool:
    """Unload a Kerbl IoT config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.kerbl.async_close()
    return unload_ok
