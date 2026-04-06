"""Diagnostics support for Wash Reminder.

Gold quality-scale requirement: diagnostics.
Accessible via Settings → Devices & Services → Wash Reminder → Download Diagnostics.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import WashReminderConfigEntry

# Redact fields that could expose personal device identifiers or preferences.
_TO_REDACT: set[str] = {"notify_target", "person_entity_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WashReminderConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    return {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(entry.data, _TO_REDACT),
            "options": async_redact_data(entry.options, _TO_REDACT),
        },
        "coordinator": {
            "trigger_entity": coordinator.trigger_entity,
            "trigger_mode": coordinator.trigger_mode,
            "trigger_state": coordinator.trigger_state_display,
            "door_sensor": coordinator.door_sensor or "(not configured)",
            "door_sensor_open_state": coordinator.door_sensor_open_state if coordinator.door_sensor else "n/a",
            "pending": coordinator.pending,
            "person_listener_active": coordinator.person_listener_active,
            "notification_task_running": coordinator.notification_task_running,
            "delivery_task_running": coordinator.delivery_task_running,
        },
    }
