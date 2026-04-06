"""Sensors for Wash Reminder."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WashReminderConfigEntry
from .coordinator import WashReminderCoordinator
from .entity import WashReminderEntity

ACTIVITY_DESCRIPTION = SensorEntityDescription(
    key="activity",
    translation_key="activity",
    entity_category=EntityCategory.DIAGNOSTIC,
)

RUNTIME_DESCRIPTION = SensorEntityDescription(
    key="runtime",
    translation_key="runtime",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WashReminderConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wash Reminder sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            WashReminderActivitySensor(coordinator),
            WashReminderRuntimeSensor(coordinator),
        ]
    )


class WashReminderActivitySensor(WashReminderEntity, SensorEntity):
    """High-level lifecycle state for dashboards and troubleshooting."""

    entity_description = ACTIVITY_DESCRIPTION

    def __init__(self, coordinator: WashReminderCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}-activity"

    @property
    def native_value(self) -> str:
        return self.coordinator.activity_state


class WashReminderRuntimeSensor(WashReminderEntity, SensorEntity):
    """Whether the integration task listeners indicate active work."""

    entity_description = RUNTIME_DESCRIPTION

    def __init__(self, coordinator: WashReminderCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}-runtime"

    @property
    def native_value(self) -> str:
        if self.coordinator.notification_task_running:
            return "reminder_loop"
        if self.coordinator.delivery_task_running:
            return "arrival_delivery"
        if self.coordinator.person_listener_active:
            return "awaiting_arrival"
        return "idle"
