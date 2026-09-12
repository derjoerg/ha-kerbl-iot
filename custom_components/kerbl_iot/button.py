"""Button platform for Kerbl IoT SmartCoop manual actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUB_DEVICE_FEEDER
from .coordinator import KerblIotConfigEntry, KerblIotDataUpdateCoordinator
from .entity import KerblIotEntity


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: KerblIotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the manual-action buttons for every SmartCoop."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    for smart_coop_id in coordinator.data:
        entities.append(KerblIotFeedButton(coordinator, smart_coop_id))
        entities.append(KerblIotAcknowledgeErrorsButton(coordinator, smart_coop_id))
    async_add_entities(entities)


class KerblIotFeedButton(KerblIotEntity, ButtonEntity):
    """Trigger one manual feeding."""

    def __init__(
        self, coordinator: KerblIotDataUpdateCoordinator, smart_coop_id: str
    ) -> None:
        """Set up the feed button on one SmartCoop's Feeder sub-device."""
        super().__init__(
            coordinator, smart_coop_id, "feed_now", sub_device=SUB_DEVICE_FEEDER
        )

    async def async_press(self) -> None:
        """Trigger one manual feeding."""
        await self.coordinator.async_trigger_feeder(self._smart_coop_id)


class KerblIotAcknowledgeErrorsButton(KerblIotEntity, ButtonEntity):
    """Acknowledge every SmartCoop error currently reported as active."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: KerblIotDataUpdateCoordinator, smart_coop_id: str
    ) -> None:
        """Set up the acknowledge-errors button for one SmartCoop."""
        super().__init__(coordinator, smart_coop_id, "acknowledge_errors")

    async def async_press(self) -> None:
        """Acknowledge every error code the SmartCoop currently reports as active.

        Active codes come from the SmartCoop's own log entries (``active``),
        not from ``current_error_reason`` -- that field is a single i18n key,
        not a numeric code the acknowledge-errors command needs.
        """
        active_codes = {
            log.error_code
            for log in self.coordinator.get_active_smart_coop_logs(self._smart_coop_id)
        }
        if not active_codes:
            raise HomeAssistantError("No active Kerbl IoT errors to acknowledge.")
        await self.coordinator.async_acknowledge_errors(
            self._smart_coop_id, sorted(active_codes)
        )
