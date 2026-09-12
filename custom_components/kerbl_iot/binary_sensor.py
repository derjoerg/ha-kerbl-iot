"""Binary sensor platform for Kerbl IoT SmartCoop on/off diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from kerbl_iot import SmartCoop

from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity


@dataclass(frozen=True, kw_only=True)
class KerblIotBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a Kerbl IoT binary sensor derived from a SmartCoop snapshot."""

    value_fn: Callable[[SmartCoop], bool | None]


def _feed_empty(smart_coop: SmartCoop) -> bool | None:
    is_feed_full = smart_coop.feeder.is_feed_full
    return None if is_feed_full is None else not is_feed_full


BINARY_SENSOR_DESCRIPTIONS: tuple[KerblIotBinarySensorEntityDescription, ...] = (
    KerblIotBinarySensorEntityDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.online,
    ),
    KerblIotBinarySensorEntityDescription(
        key="feeding_in_progress",
        translation_key="feeding_in_progress",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda smart_coop: smart_coop.feeder.feeding_in_progress,
    ),
    KerblIotBinarySensorEntityDescription(
        key="feed_empty",
        translation_key="feed_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Kerbl reports whether the feeder is full, not whether it's empty;
        # a PROBLEM binary sensor is expected to read "on" for the problem
        # case, so this is deliberately inverted from the raw API value.
        value_fn=_feed_empty,
    ),
    KerblIotBinarySensorEntityDescription(
        key="feeding_locked",
        translation_key="feeding_locked",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.feeder.feeding_locked,
    ),
    KerblIotBinarySensorEntityDescription(
        key="water_sensor",
        translation_key="water_sensor",
        # Best-effort mapping: Kerbl doesn't document whether "on" means
        # water present (as MOISTURE assumes) or a fault; treated as the
        # former since the field lives on the water heater, not on a leak
        # detector.
        device_class=BinarySensorDeviceClass.MOISTURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.water_heater.water_sensor_state,
    ),
    KerblIotBinarySensorEntityDescription(
        key="external_brightness_sensor",
        translation_key="external_brightness_sensor",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.brightness.external_sensor_connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SmartCoop binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        KerblIotBinarySensor(coordinator, smart_coop_id, description)
        for smart_coop_id in coordinator.data
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class KerblIotBinarySensor(KerblIotEntity, BinarySensorEntity):
    """A single SmartCoop on/off diagnostic value."""

    entity_description: KerblIotBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: KerblIotDataUpdateCoordinator,
        smart_coop_id: str,
        description: KerblIotBinarySensorEntityDescription,
    ) -> None:
        """Set up one binary sensor for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the sensor's current state, or None if the device is gone."""
        smart_coop = self.smart_coop
        if smart_coop is None:
            return None
        return self.entity_description.value_fn(smart_coop)
