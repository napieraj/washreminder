"""Wash Reminder — persistent, presence-gated washer notifications."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WashReminderCoordinator

PLATFORMS: list[str] = ["binary_sensor", "sensor"]

# Python 3.12 type alias (PEP 695). HA 2025.1+ mandates Python 3.12.
# Propagates type safety into platform setup functions with zero runtime cost.
type WashReminderConfigEntry = ConfigEntry[WashReminderCoordinator]


async def _async_reload_on_update(
    hass: HomeAssistant, entry: WashReminderConfigEntry
) -> None:
    """Reload when options change so coordinator picks up new timing values."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: WashReminderConfigEntry) -> bool:
    """Set up Wash Reminder from a config entry."""
    coordinator = WashReminderCoordinator(hass, entry)
    await coordinator.async_setup()

    # runtime_data replaces hass.data[DOMAIN] — mandatory quality-scale rule
    # since HA 2025.1. Auto-cleared by HA on successful unload.
    entry.runtime_data = coordinator

    # Options-change listener. add_update_listener returns its own unsub
    # callable; wrapping in async_on_unload ensures it's cleaned up on unload.
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: WashReminderConfigEntry) -> bool:
    """Unload a config entry.

    All cleanup is managed by the ConfigEntry lifecycle:
    - Trigger entity listener: registered via entry.async_on_unload() in coordinator
    - Door sensor listener: registered via entry.async_on_unload() in coordinator
    - Person entity listener: registered via entry.async_on_unload() in coordinator
    - Background tasks: auto-cancelled via entry._background_tasks
    - runtime_data: auto-cleared by HA on return of True
    - Options listener: entry.async_on_unload registered above
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
