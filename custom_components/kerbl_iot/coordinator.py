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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from kerbl_iot import (
    KerblAuthenticationError,
    KerblConnectionError,
    KerblIOT,
    KerblProtocolError,
    KerblStateError,
    SmartCoop,
)

from .const import DOMAIN

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
        kerbl.register_smart_coop_update_callback(self._handle_push_update)
        kerbl.register_availability_callback(self._handle_availability_change)

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

    def is_smart_coop_available(self, smart_coop_id: str) -> bool:
        """Return whether a given SmartCoop is currently reachable.

        Entities should use this -- not ``coordinator.last_update_success``
        -- for their ``available`` property: a config entry with several
        SmartCoops can have one drop offline while the others (and the
        account's REST/Socket.IO connection as a whole) stay fine.
        """
        return self.kerbl.is_smart_coop_available(smart_coop_id)

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
