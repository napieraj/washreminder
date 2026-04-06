"""Binary sensors for Wash Reminder."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WashReminderConfigEntry
from .coordinator import WashReminderCoordinator
from .entity import WashReminderEntity

PENDING_DESCRIPTION = BinarySensorEntityDescription(
    key="pending_notification",
    translation_key="pending_notification",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WashReminderConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wash Reminder binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities([WashReminderPendingBinarySensor(coordinator)])


class WashReminderPendingBinarySensor(WashReminderEntity, BinarySensorEntity):
    """On while a notification is deferred until the person arrives home."""

    entity_description = PENDING_DESCRIPTION

    def __init__(self, coordinator: WashReminderCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}-pending_notification"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.pending
