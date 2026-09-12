"""DataUpdateCoordinator for Kerbl IoT SmartCoop devices.

Kerbl IoT devices push their state over a Socket.IO connection the instant
something changes (``KerblIOT.register_smart_coop_update_callback``), so
this coordinator is push-driven rather than poll-driven: ``update_interval``
below only exists as a fallback for whenever that connection is down,
missed an event, or hasn't connected yet.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from kerbl_iot import (
    KerblAuthenticationError,
    KerblConnectionError,
    KerblIOT,
    KerblProtocolError,
    KerblStateError,
    SmartCoop,
    SmartCoopLog,
)

from .const import DOMAIN, MANUFACTURER, MODEL, SUB_DEVICE_DOOR, SUB_DEVICES

_LOGGER = logging.getLogger(__name__)

# SmartCoops push their state the instant it changes; this interval is only
# the fallback cadence for whenever the Socket.IO channel is down, missed an
# event, or hasn't connected yet -- 15-20 minutes keeps a genuinely offline
# device from going unnoticed for too long without polling any more than
# that push-first design actually needs.
FALLBACK_UPDATE_INTERVAL = timedelta(minutes=17)

# Referenced by KerblIotDataUpdateCoordinator.config_entry below, before the
# class itself is defined -- ConfigEntry accepts a forward-reference string
# for its type parameter without evaluating it eagerly, same as any other
# generic. (TypeAlias -- not the newer PEP 695 `type` statement -- to stay
# parseable by every mypy version this project's toolchain runs, per the
# UP040 note in pyproject.toml.)
KerblIotConfigEntry: TypeAlias = ConfigEntry["KerblIotDataUpdateCoordinator"]


class KerblIotDataUpdateCoordinator(DataUpdateCoordinator[dict[str, SmartCoop]]):
    """Keep one account's SmartCoop devices current via push updates and polling."""

    config_entry: KerblIotConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: KerblIotConfigEntry, kerbl: KerblIOT
    ) -> None:
        """Wrap an already token-restored ``KerblIOT`` for one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} ({config_entry.title})",
            update_interval=FALLBACK_UPDATE_INTERVAL,
        )
        self.kerbl = kerbl
        # Populated by _async_register_smart_coop_devices(), before any
        # entity platform runs: maps a SmartCoop's own ID to the internal
        # device registry ID Home Assistant assigned its root device.
        # Nothing outside this coordinator currently needs it -- entities
        # match their pre-registered device by `identifiers`, not this ID
        # -- but it's kept as a small, cheap-to-maintain hook for anything
        # that later needs the root device without a registry lookup (e.g.
        # diagnostics).
        self.smart_coop_device_ids: dict[str, str] = {}
        kerbl.register_smart_coop_update_callback(self._handle_push_update)
        kerbl.register_availability_callback(self._handle_availability_change)
        kerbl.register_smart_coop_log_callback(self._handle_log_refresh)

    async def _async_setup(self) -> None:
        """Validate the stored session and open the Socket.IO push channel.

        Runs once, before the first ``_async_update_data``. Loading here
        explicitly -- rather than relying on ``connect_websocket()``'s own
        "load if I don't have any devices yet" fallback -- means a stale or
        revoked token surfaces the same ``ConfigEntryAuthFailed`` /
        ``UpdateFailed`` Home Assistant expects from any first refresh,
        instead of an unrelated-looking websocket-connect failure.
        """
        await self._async_load()
        self._async_register_smart_coop_devices()
        try:
            await self.kerbl.connect_websocket()
        except KerblConnectionError:
            # Not fatal: _async_update_data()'s polling fallback below keeps
            # entities current, and KerblIOT's own Socket.IO client keeps
            # retrying the connection on its own schedule in the background.
            _LOGGER.warning(
                "Kerbl IoT push channel unavailable for %s; falling back to "
                "polling every %s",
                self.config_entry.title,
                FALLBACK_UPDATE_INTERVAL,
            )

    def _async_register_smart_coop_devices(self) -> None:
        """Pre-register each SmartCoop's root and sub-devices, and link them.

        Sub-devices are linked back to their SmartCoop root device via
        ``via_device_id``: the *internal*, already-assigned device registry
        ID of the root device -- not the older, now-deprecated ``via_device``
        identifier-tuple form. Setting it is done here, through
        ``async_update_device``, rather than via each sub-device entity's own
        ``device_info`` (the more obviously "entity-owned" way to do it):
        ``via_device_id`` has been a stable ``async_update_device`` parameter
        since long before this integration's declared minimum Home Assistant
        version (2024.12.0), whereas the ``DeviceInfo`` TypedDict entities
        populate their ``device_info`` from has only just started gaining a
        ``via_device_id`` key on some installs and not, as of this writing,
        on others -- mypy rejects it as an unknown key wherever it hasn't
        landed yet. Doing the linking here avoids depending on that
        still-rolling-out surface entirely.

        Entities still declare their own ``device_info`` for both the root
        device and each sub-device (matched back to the devices created here
        by their shared ``identifiers``), so keeping fields like name,
        sw_version or translation_key current stays entirely their job --
        this only needs the devices to exist, linked, before any entity
        platform (and therefore any sub-device entity) is set up.
        """
        device_registry = dr.async_get(self.hass)
        for smart_coop in self.kerbl.smart_coops:
            root_device = device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, smart_coop.id)},
                name=smart_coop.name,
                manufacturer=MANUFACTURER,
                model=MODEL,
                sw_version=smart_coop.firmware_version,
            )
            self.smart_coop_device_ids[smart_coop.id] = root_device.id

            for sub_device in SUB_DEVICES:
                # A SmartCoop reporting no door (hasNoDoor) gets no Door
                # device at all -- not just no entities on it -- matching
                # the door platforms' own has_no_door check (cover.py,
                # sensor.py).
                is_missing_door = (
                    sub_device == SUB_DEVICE_DOOR
                    and smart_coop.door.has_no_door is True
                )
                if is_missing_door:
                    continue
                sub_device_entry = device_registry.async_get_or_create(
                    config_entry_id=self.config_entry.entry_id,
                    identifiers={(DOMAIN, f"{smart_coop.id}_{sub_device}")},
                    translation_key=sub_device,
                    manufacturer=MANUFACTURER,
                )
                device_registry.async_update_device(
                    sub_device_entry.id, via_device_id=root_device.id
                )

    async def _async_update_data(self) -> dict[str, SmartCoop]:
        """Poll fallback: re-fetch every SmartCoop for this account over REST."""
        await self._async_load()
        return self._smart_coops_by_id()

    async def _async_load(self) -> None:
        """Load SmartCoops, translating client errors to Home Assistant's."""
        try:
            await self.kerbl.load()
        except KerblAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Kerbl IoT session expired; reauthentication required."
            ) from err
        except (KerblConnectionError, KerblProtocolError) as err:
            raise UpdateFailed(
                f"Kerbl IoT service is currently unreachable: {err}"
            ) from err

    def _smart_coops_by_id(self) -> dict[str, SmartCoop]:
        """Return the currently loaded SmartCoops keyed by their ID."""
        return {smart_coop.id: smart_coop for smart_coop in self.kerbl.smart_coops}

    async def _handle_push_update(self, smart_coop: SmartCoop) -> None:  # noqa: ARG002 - state already updated in place, see below
        """Feed a Socket.IO push update straight to coordinator listeners.

        ``smart_coop`` was already merged into the matching stable instance
        (see ``KerblIOT._handle_smart_coop_update``), so ``self.kerbl`` is
        already current; this only needs to hand a fresh snapshot dict to
        ``async_set_updated_data`` so subscribed entities re-render.
        """
        self.async_set_updated_data(self._smart_coops_by_id())

    async def _handle_availability_change(
        self,
        smart_coop: SmartCoop,  # noqa: ARG002 - entities read availability from the coordinator, not this callback
        available: bool,  # noqa: ARG002 - see above
    ) -> None:
        """Re-notify listeners so per-device availability (see below) updates."""
        self.async_update_listeners()

    async def _handle_log_refresh(
        self,
        smart_coop: SmartCoop,  # noqa: ARG002 - entities read logs via get_active_smart_coop_logs, not this callback
        logs: list[SmartCoopLog],  # noqa: ARG002 - see above
    ) -> None:
        """Re-notify listeners so the has-errors binary sensor picks up new logs.

        ``KerblIOT`` refreshes its authoritative log cache in the
        background -- debounced, shortly after a SmartCoop update changes
        its error fields (see ``KerblIOT._schedule_log_refresh``) -- on a
        callback list of its own, separate from the SmartCoop push-update
        callbacks ``_handle_push_update`` above already listens to. Without
        also registering here, a newly active error would sit in
        ``self.kerbl``'s cache without ever reaching listening entities.
        """
        self.async_update_listeners()

    def is_smart_coop_available(self, smart_coop_id: str) -> bool:
        """Return whether a given SmartCoop is currently reachable.

        Entities should use this -- not ``coordinator.last_update_success``
        -- for their ``available`` property: a config entry with several
        SmartCoops can have one drop offline while the others (and the
        account's REST/Socket.IO connection as a whole) stay fine.
        """
        return self.kerbl.is_smart_coop_available(smart_coop_id)

    def get_active_smart_coop_logs(self, smart_coop_id: str) -> list[SmartCoopLog]:
        """Return a SmartCoop's currently active (unacknowledged) log entries.

        Shared by the has-errors binary sensor (state + the active errors
        it reports as an attribute) and the acknowledge-errors button
        (which codes to send), so both agree on what "active" means.
        """
        return [
            log for log in self.kerbl.get_smart_coop_logs(smart_coop_id) if log.active
        ]

    async def async_turn_on_light(self, smart_coop_id: str) -> None:
        """Turn a SmartCoop's light on and push the confirmed state."""
        await self._async_run_command(smart_coop_id, lambda coop: coop.light.turn_on())

    async def async_turn_off_light(self, smart_coop_id: str) -> None:
        """Turn a SmartCoop's light off and push the confirmed state."""
        await self._async_run_command(smart_coop_id, lambda coop: coop.light.turn_off())

    async def async_open_door(self, smart_coop_id: str) -> None:
        """Open a SmartCoop's door and push the confirmed state."""
        await self._async_run_command(smart_coop_id, lambda coop: coop.door.open())

    async def async_close_door(self, smart_coop_id: str) -> None:
        """Close a SmartCoop's door and push the confirmed state."""
        await self._async_run_command(smart_coop_id, lambda coop: coop.door.close())

    async def async_trigger_feeder(self, smart_coop_id: str) -> None:
        """Trigger one manual feeding and push the confirmed state."""
        await self._async_run_command(smart_coop_id, lambda coop: coop.feeder.press())

    async def async_acknowledge_errors(
        self, smart_coop_id: str, error_codes: list[int]
    ) -> None:
        """Acknowledge active SmartCoop error codes and push the confirmed state."""
        await self._async_run_command(
            smart_coop_id, lambda coop: coop.acknowledge_errors(error_codes)
        )

    async def _async_run_command(
        self,
        smart_coop_id: str,
        command: Callable[[SmartCoop], Awaitable[Any]],
    ) -> None:
        """Run one SmartCoop command, then push whatever state it confirmed.

        Pushes the latest known state in a ``finally`` -- even a failed or
        timed-out command (e.g. a door that never reached the requested
        state) can have changed what the device last reported, so entities
        should see that either way. Failures surface as
        ``HomeAssistantError``, which Home Assistant's service-call handling
        turns into a user-visible error without the caller needing to know
        about kerbl-iot's own exception types.
        """
        smart_coop = self.kerbl.get_smart_coop(smart_coop_id)
        if smart_coop is None:
            raise HomeAssistantError(f"Unknown Kerbl IoT SmartCoop: {smart_coop_id}")
        try:
            await command(smart_coop)
        except (KerblConnectionError, KerblProtocolError) as err:
            raise HomeAssistantError(f"Kerbl IoT command failed: {err}") from err
        except KerblStateError as err:
            raise HomeAssistantError(str(err)) from err
        except TimeoutError as err:
            raise HomeAssistantError(
                "Kerbl IoT device did not confirm the command in time."
            ) from err
        finally:
            self.async_set_updated_data(self._smart_coops_by_id())
