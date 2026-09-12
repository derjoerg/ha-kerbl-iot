"""Shared base entity for Kerbl IoT SmartCoop entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from kerbl_iot import SmartCoop

from .const import DOMAIN
from .coordinator import KerblIotDataUpdateCoordinator

MANUFACTURER = "Kerbl"
MODEL = "SmartCoop"


class KerblIotEntity(CoordinatorEntity[KerblIotDataUpdateCoordinator]):
    """Base entity for one of a SmartCoop's sub-components.

    Every entity platform in this integration is keyed off a SmartCoop ID
    rather than the coordinator's single ``data`` blob directly: one config
    entry (one Kerbl account) can have several SmartCoops, and every entity
    -- the light, the door, the feed button, the sensors -- belongs to
    exactly one of them.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KerblIotDataUpdateCoordinator,
        smart_coop_id: str,
        translation_key: str,
    ) -> None:
        """Set up the entity for one SmartCoop and one of its sub-components."""
        super().__init__(coordinator)
        self._smart_coop_id = smart_coop_id
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{smart_coop_id}_{translation_key}"
        # A snapshot taken once at setup: sw_version can go stale if the
        # firmware updates later without a reload, which is an acceptable
        # trade-off for how rarely that happens versus the complexity of
        # keeping the device registry live-updated from here.
        smart_coop = coordinator.data[smart_coop_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, smart_coop_id)},
            name=smart_coop.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=smart_coop.firmware_version,
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
