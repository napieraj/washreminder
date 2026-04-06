"""Shared entity base for Wash Reminder platforms."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import WashReminderCoordinator


class WashReminderEntity(Entity):
    """Base entity wired to the coordinator listener bus."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WashReminderCoordinator) -> None:
        self.coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name="Wash Reminder",
            manufacturer="Wash Reminder",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
