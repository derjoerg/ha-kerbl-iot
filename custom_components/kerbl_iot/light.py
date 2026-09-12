"""Light platform for Kerbl IoT SmartCoop lights."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one light per SmartCoop."""
    coordinator = entry.runtime_data
    async_add_entities(
        KerblIotLight(coordinator, smart_coop_id) for smart_coop_id in coordinator.data
    )


class KerblIotLight(KerblIotEntity, LightEntity):
    """A SmartCoop's manually controllable light.

    Kerbl only exposes a manual on/off command (and a reported dim value
    that isn't independently settable), so this supports on/off only --
    no brightness, color, or effect control.
    """

    _attr_color_mode = ColorMode.ONOFF
    # LightEntity declares this as an instance attribute (not a ClassVar), so
    # it can't be narrowed to ClassVar here without mypy's "Cannot override
    # instance variable with class variable" error. Nothing ever mutates this
    # set in place, so sharing one frozen set of values across instances is
    # safe despite ruff's usual mutable-default suspicion.
    _attr_supported_color_modes: set[ColorMode] | None = {ColorMode.ONOFF}  # noqa: RUF012

    def __init__(
        self, coordinator: KerblIotDataUpdateCoordinator, smart_coop_id: str
    ) -> None:
        """Set up the light entity for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, "light")

    @property
    def is_on(self) -> bool | None:
        """Return whether the light is currently reported on."""
        smart_coop = self.smart_coop
        return None if smart_coop is None else smart_coop.light.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002 - no supported turn-on options
        """Turn the light on and wait for Kerbl to confirm it."""
        await self.coordinator.async_turn_on_light(self._smart_coop_id)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002 - no supported turn-off options
        """Turn the light off and wait for Kerbl to confirm it."""
        await self.coordinator.async_turn_off_light(self._smart_coop_id)
