"""Binary sensor platform for Kerbl IoT SmartCoop on/off diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from kerbl_iot import SmartCoop

from .const import SUB_DEVICE_BRIGHTNESS, SUB_DEVICE_FEEDER, SUB_DEVICE_WATER_HEATER
from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity


@dataclass(frozen=True, kw_only=True)
class KerblIotBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a Kerbl IoT binary sensor derived from a SmartCoop snapshot."""

    value_fn: Callable[[SmartCoop], bool | None]
    # Which of the SmartCoop's sub-devices (see entity.py) this sensor
    # belongs to; None keeps it on the SmartCoop root device.
    sub_device: str | None = None


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
        sub_device=SUB_DEVICE_FEEDER,
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda smart_coop: smart_coop.feeder.feeding_in_progress,
    ),
    KerblIotBinarySensorEntityDescription(
        key="feed_empty",
        translation_key="feed_empty",
        sub_device=SUB_DEVICE_FEEDER,
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
        sub_device=SUB_DEVICE_FEEDER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda smart_coop: smart_coop.feeder.feeding_locked,
    ),
    KerblIotBinarySensorEntityDescription(
        key="water_sensor",
        translation_key="water_sensor",
        sub_device=SUB_DEVICE_WATER_HEATER,
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
        sub_device=SUB_DEVICE_BRIGHTNESS,
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
    entities: list[BinarySensorEntity] = []
    for smart_coop_id in coordinator.data:
        entities.append(KerblIotHasErrorsBinarySensor(coordinator, smart_coop_id))
        entities.extend(
            KerblIotBinarySensor(coordinator, smart_coop_id, description)
            for description in BINARY_SENSOR_DESCRIPTIONS
        )
    async_add_entities(entities)


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
        super().__init__(
            coordinator,
            smart_coop_id,
            description.key,
            sub_device=description.sub_device,
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the sensor's current state, or None if the device is gone."""
        smart_coop = self.smart_coop
        if smart_coop is None:
            return None
        return self.entity_description.value_fn(smart_coop)


class KerblIotHasErrorsBinarySensor(KerblIotEntity, BinarySensorEntity):
    """Whether a SmartCoop currently reports any active error.

    Lives on the SmartCoop root device, not a sub-device: Kerbl's error log
    isn't scoped to one component (a water heater fault and a door fault
    show up in the same log), so there's no single sub-device it more
    naturally belongs to.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: KerblIotDataUpdateCoordinator, smart_coop_id: str
    ) -> None:
        """Set up the has-errors binary sensor for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, "has_errors")

    @property
    def is_on(self) -> bool | None:
        """Return whether any SmartCoop error is currently active."""
        if self.smart_coop is None:
            return None
        return bool(self.coordinator.get_active_smart_coop_logs(self._smart_coop_id))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the active errors as a list of {code, key} entries.

        ``key`` is the i18n key Kerbl's own app would resolve to a message
        (e.g. "err.some_error"); kerbl-iot doesn't resolve it to text
        itself, so this is the most useful structured form available.
        """
        if self.smart_coop is None:
            return None
        return {
            "active_errors": [
                {"code": log.error_code, "key": log.error_key}
                for log in self.coordinator.get_active_smart_coop_logs(
                    self._smart_coop_id
                )
            ]
        }
