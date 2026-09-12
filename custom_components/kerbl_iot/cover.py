"""Cover platform for Kerbl IoT SmartCoop doors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from kerbl_iot import DoorState

from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity

# (is_closed, is_opening, is_closing) for the door states that map onto a
# clear cover position. States outside this map (SIMULATE, TOGGLE_MANUAL,
# UNLOCK, LOCK_UNTIL_TOMORROW, LOCK_PERMANENTLY, UNKNOWN) are Kerbl-specific
# lock/manual modes with no equivalent open/closed position, so the cover
# reports an unknown position for them rather than guessing one.
_COVER_POSITION: dict[DoorState, tuple[bool | None, bool, bool]] = {
    DoorState.OPEN: (False, False, False),
    DoorState.CLOSED: (True, False, False),
    DoorState.OPENING: (None, True, False),
    DoorState.CLOSING: (None, False, True),
}
_UNKNOWN_POSITION: tuple[bool | None, bool, bool] = (None, False, False)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one cover per SmartCoop that reports actually having a door."""
    coordinator = entry.runtime_data
    async_add_entities(
        KerblIotDoorCover(coordinator, smart_coop_id)
        for smart_coop_id, smart_coop in coordinator.data.items()
        if smart_coop.door.has_no_door is not True
    )


class KerblIotDoorCover(KerblIotEntity, CoverEntity):
    """A SmartCoop's automatic door."""

    _attr_device_class = CoverDeviceClass.DOOR
    # Kerbl's door only exposes full open/close commands, not a partial
    # position or a mid-travel stop.
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self, coordinator: KerblIotDataUpdateCoordinator, smart_coop_id: str
    ) -> None:
        """Set up the door cover entity for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, "door")

    @property
    def is_closed(self) -> bool | None:
        """Return whether the door is fully closed."""
        return self._position[0]

    @property
    def is_opening(self) -> bool:
        """Return whether the door is currently opening."""
        return self._position[1]

    @property
    def is_closing(self) -> bool:
        """Return whether the door is currently closing."""
        return self._position[2]

    @property
    def _position(self) -> tuple[bool | None, bool, bool]:
        smart_coop = self.smart_coop
        if smart_coop is None or smart_coop.door.state is None:
            return _UNKNOWN_POSITION
        return _COVER_POSITION.get(smart_coop.door.state, _UNKNOWN_POSITION)

    async def async_open_cover(self, **kwargs: Any) -> None:  # noqa: ARG002 - no supported open options
        """Open the door and wait for Kerbl to confirm it."""
        await self.coordinator.async_open_door(self._smart_coop_id)

    async def async_close_cover(self, **kwargs: Any) -> None:  # noqa: ARG002 - no supported close options
        """Close the door and wait for Kerbl to confirm it."""
        await self.coordinator.async_close_door(self._smart_coop_id)
