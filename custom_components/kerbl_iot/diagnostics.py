"""Diagnostics support for the Kerbl IoT integration.

Two levels are exposed, both discovered automatically by Home Assistant's
diagnostics integration from the presence of this module (no manifest flag
needed): a config-entry download (via the "..." menu on the integration's
page) and, per SmartCoop, a device download (via the "..." menu on that
device's page). Both delegate the actual device/log payload to kerbl-iot's
own ``to_diagnostics()`` helpers (see ``SmartCoop.to_diagnostics`` /
``KerblIOT.to_diagnostics`` in the library) and then redact anything that
identifies the Kerbl *account* rather than describing device state.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator

# Config entry fields that either identify the Kerbl account (email) or
# would grant access to it if leaked (the token pair). The password itself
# is never stored on the entry in the first place (see config_flow.py).
TO_REDACT_ENTRY_DATA = {CONF_EMAIL, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN}

# Fields inside kerbl-iot's own diagnostics payload that identify the Kerbl
# *account* rather than describe SmartCoop device state. The SmartCoop's own
# `id` and user-assigned `name` are left in: they're needed to tell devices
# apart and to cross-reference against Kerbl support tickets, and neither
# one identifies the account the way `user_id` does.
TO_REDACT_KERBL_DATA = {"user_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for one Kerbl IoT config entry (one account)."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            # Neither `title` nor `unique_id` is included as-is: this
            # integration's config flow sets the entry title to
            # f"Kerbl IoT ({email})" and its unique_id to the lowercased
            # email itself (see config_flow.py), so both are as sensitive
            # as CONF_EMAIL -- and neither is inside entry.data, so
            # async_redact_data below wouldn't catch them anyway. REDACTED
            # (vs. None) still shows whether one was set, which is enough
            # to debug entry-setup issues without exposing the address.
            "title": REDACTED if entry.title else None,
            "unique_id": REDACTED if entry.unique_id else None,
            "data": async_redact_data(entry.data, TO_REDACT_ENTRY_DATA),
        },
        "coordinator": _coordinator_diagnostics(coordinator),
        "kerbl": async_redact_data(
            _kerbl_diagnostics(coordinator), TO_REDACT_KERBL_DATA
        ),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a single SmartCoop device."""
    coordinator = entry.runtime_data
    smart_coop_id = _smart_coop_id_from_device(device)
    smart_coop = (
        coordinator.data.get(smart_coop_id) if smart_coop_id is not None else None
    )
    if smart_coop_id is None or smart_coop is None:
        return {
            "error": (f"No Kerbl IoT SmartCoop currently loaded for device {device.id}")
        }

    diagnostics: dict[str, Any] = smart_coop.to_diagnostics()
    diagnostics["available"] = coordinator.is_smart_coop_available(smart_coop_id)
    diagnostics["logs"] = [
        log.to_diagnostics()
        for log in coordinator.kerbl.get_smart_coop_logs(smart_coop_id)
    ]
    return async_redact_data(diagnostics, TO_REDACT_KERBL_DATA)


def _coordinator_diagnostics(
    coordinator: KerblIotDataUpdateCoordinator,
) -> dict[str, Any]:
    """Return the coordinator's own health, independent of any one device."""
    update_interval = coordinator.update_interval
    last_exception = coordinator.last_exception
    return {
        "last_update_success": coordinator.last_update_success,
        "last_exception": str(last_exception) if last_exception else None,
        "update_interval_seconds": (
            update_interval.total_seconds() if update_interval else None
        ),
    }


def _kerbl_diagnostics(coordinator: KerblIotDataUpdateCoordinator) -> dict[str, Any]:
    """Return kerbl-iot's own diagnostics, enriched with per-device availability.

    ``KerblIOT.to_diagnostics()`` reports each SmartCoop's ``online`` flag
    and the account's overall ``websocket_connected`` state, but not the
    combination of the two that actually drives an entity's ``available``
    property (see ``KerblIotEntity.available`` in entity.py) -- add it
    explicitly so diagnostics reflect what users actually see in the UI.
    """
    diagnostics = coordinator.kerbl.to_diagnostics()
    for smart_coop_data in diagnostics["smart_coops"]:
        smart_coop_data["available"] = coordinator.is_smart_coop_available(
            smart_coop_data["id"]
        )
    return diagnostics


def _smart_coop_id_from_device(device: DeviceEntry) -> str | None:
    """Return the SmartCoop ID encoded in a device's identifiers, if any."""
    return next(
        (identifier for domain, identifier in device.identifiers if domain == DOMAIN),
        None,
    )
