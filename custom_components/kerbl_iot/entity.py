"""Shared base entity for Kerbl IoT SmartCoop entities and their sub-devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from kerbl_iot import SmartCoop

from .const import DOMAIN
from .coordinator import KerblIotDataUpdateCoordinator

MANUFACTURER = "Kerbl"
MODEL = "SmartCoop"

# Kerbl's SmartCoop is itself made up of distinct physical components -- a
# door, a light, a feeder, a water heater, a brightness sensor -- each with
# its own entities. Rather than putting all of their entities on one flat
# SmartCoop device, each becomes its own Home Assistant device, linked back
# to the SmartCoop root device via `via_device` (own device page, own area
# assignment, own diagnostics download). These are the device-identifier
# suffixes and `translation_key`s for the five sub-devices every SmartCoop
# has; pass one of them as `sub_device` to `KerblIotEntity.__init__` to put
# an entity on that device instead of on the SmartCoop root device.
SUB_DEVICE_DOOR = "door"
SUB_DEVICE_LIGHT = "light"
SUB_DEVICE_FEEDER = "feeder"
SUB_DEVICE_WATER_HEATER = "water_heater"
SUB_DEVICE_BRIGHTNESS = "brightness"


class KerblIotEntity(CoordinatorEntity[KerblIotDataUpdateCoordinator]):
    """Base entity for one SmartCoop or one of its sub-component devices."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KerblIotDataUpdateCoordinator,
        smart_coop_id: str,
        translation_key: str | None,
        *,
        sub_device: str | None = None,
    ) -> None:
        """Set up the entity for one SmartCoop, or one of its sub-devices.

        ``translation_key`` may only be ``None`` for an entity that is the
        sole, primary representation of its device (e.g. the door's cover
        entity): Home Assistant then shows the device's own translated name
        for the entity instead of the redundant "Door Door". At least one of
        ``translation_key`` or ``sub_device`` must be given, since the
        unique_id is derived from whichever one identifies this entity.

        ``sub_device`` (one of the ``SUB_DEVICE_*`` constants above) puts
        the entity on its own device, linked to the SmartCoop root device --
        matching Kerbl's own device model of a SmartCoop with a door, a
        light, a feeder, a water heater and a brightness sensor as distinct
        components. Leaving it ``None`` keeps the entity on the SmartCoop
        root device itself, for state describing the whole unit rather than
        one component (e.g. air temperature, or whether any error is
        active).
        """
        super().__init__(coordinator)
        self._smart_coop_id = smart_coop_id
        self._attr_translation_key = translation_key
        unique_id_key = translation_key or sub_device
        if unique_id_key is None:
            raise ValueError(
                "KerblIotEntity needs a translation_key, a sub_device, or both."
            )
        self._attr_unique_id = f"{smart_coop_id}_{unique_id_key}"

        if sub_device is None:
            # A snapshot taken once at setup: sw_version can go stale if the
            # firmware updates later without a reload, an acceptable
            # trade-off against the complexity of keeping the device
            # registry live-updated from here.
            smart_coop = coordinator.data[smart_coop_id]
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, smart_coop_id)},
                name=smart_coop.name,
                manufacturer=MANUFACTURER,
                model=MODEL,
                sw_version=smart_coop.firmware_version,
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{smart_coop_id}_{sub_device}")},
                # `via_device` (an identifier tuple) rather than the newer
                # `via_device_id` (the parent device's internal registry
                # ID): `via_device` is deprecated on very recent Home
                # Assistant releases in favor of `via_device_id`, but still
                # works today -- a logged warning for custom integrations,
                # not an error, see homeassistant.helpers.frame.report_usage
                # -- and unlike `via_device_id` it doesn't require this
                # integration to bump its declared minimum Home Assistant
                # version (hacs.json: 2024.12.0) just to link sub-devices to
                # their SmartCoop.
                via_device=(DOMAIN, smart_coop_id),
                translation_key=sub_device,
                manufacturer=MANUFACTURER,
            )

    @property
    def smart_coop(self) -> SmartCoop | None:
        """Return this entity's current SmartCoop, if it's still loaded."""
        return self.coordinator.data.get(self._smart_coop_id)

    @property
    def available(self) -> bool:
        """Return whether the account and this specific SmartCoop are up.

        Deliberately not just ``coordinator.last_update_success``: an
        account with several SmartCoops can have one of them drop offline
        while the account's own REST/Socket.IO connection, and its other
        SmartCoops, stay perfectly fine.
        """
        return (
            super().available
            and self.smart_coop is not None
            and self.coordinator.is_smart_coop_available(self._smart_coop_id)
        )
