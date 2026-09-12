"""Sensor platform for Kerbl IoT SmartCoop measurements and diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from kerbl_iot import DoorState, SmartCoop

from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity

_DOOR_STATE_OPTIONS = [state.name.lower() for state in DoorState]
# These two only make sense for a SmartCoop that actually reports a door.
_DOOR_ONLY_KEYS = frozenset({"door_closes_in", "door_state"})


@dataclass(frozen=True, kw_only=True)
class KerblIotSensorEntityDescription(SensorEntityDescription):
    """Describe a Kerbl IoT sensor derived from a SmartCoop snapshot."""

    value_fn: Callable[[SmartCoop], StateType]


def _door_state_option(smart_coop: SmartCoop) -> StateType:
    state = smart_coop.door.state
    return None if state is None else state.name.lower()


SENSOR_DESCRIPTIONS: tuple[KerblIotSensorEntityDescription, ...] = (
    KerblIotSensorEntityDescription(
        key="air_temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda smart_coop: smart_coop.air_temperature,
    ),
    KerblIotSensorEntityDescription(
        key="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda smart_coop: smart_coop.water_heater.water_temperature,
    ),
    KerblIotSensorEntityDescription(
        key="brightness",
        translation_key="brightness",
        # Kerbl doesn't document a unit for the reported value, so this is
        # left as a plain numeric measurement rather than guessing lux/%.
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.brightness.current_brightness,
    ),
    KerblIotSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.firmware_version,
    ),
    KerblIotSensorEntityDescription(
        key="door_closes_in",
        translation_key="door_closes_in",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda smart_coop: smart_coop.door.closes_in_minutes,
    ),
    KerblIotSensorEntityDescription(
        key="door_state",
        translation_key="door_state",
        device_class=SensorDeviceClass.ENUM,
        options=_DOOR_STATE_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_door_state_option,
    ),
    KerblIotSensorEntityDescription(
        key="current_error",
        translation_key="current_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.current_error_reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SmartCoop sensors, skipping door-only ones without a door."""
    coordinator = entry.runtime_data
    entities: list[KerblIotSensor] = []
    for smart_coop_id, smart_coop in coordinator.data.items():
        has_door = smart_coop.door.has_no_door is not True
        for description in SENSOR_DESCRIPTIONS:
            if description.key in _DOOR_ONLY_KEYS and not has_door:
                continue
            entities.append(KerblIotSensor(coordinator, smart_coop_id, description))
    async_add_entities(entities)


class KerblIotSensor(KerblIotEntity, SensorEntity):
    """A single read-only SmartCoop measurement or diagnostic value."""

    entity_description: KerblIotSensorEntityDescription

    def __init__(
        self,
        coordinator: KerblIotDataUpdateCoordinator,
        smart_coop_id: str,
        description: KerblIotSensorEntityDescription,
    ) -> None:
        """Set up one sensor for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor's current value, or None if the device is gone."""
        smart_coop = self.smart_coop
        if smart_coop is None:
            return None
        return self.entity_description.value_fn(smart_coop)
