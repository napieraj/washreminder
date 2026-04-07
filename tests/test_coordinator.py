"""Tests for Wash Reminder coordinator lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.washreminder.const import (
    ACTION_DONE,
    ACTION_SNOOZE,
    CONF_ARRIVAL_DELAY_SECONDS,
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_INVERTED,
    CONF_MAX_REPEATS,
    CONF_NOTIFY_TARGET,
    CONF_PERSON,
    CONF_REPEAT_INTERVAL_MINUTES,
    CONF_SNOOZE_MINUTES,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_MODE,
    CONF_TRIGGER_STATE,
    CONF_WASHDATA_ENTRY_ID,
    DOMAIN,
    EVENT_NOTIFICATION_ACTION,
    EVENT_WASHDATA_CYCLE_ENDED,
    TRIGGER_MODE_BINARY_SENSOR,
    TRIGGER_MODE_STATE_SENSOR,
    TRIGGER_MODE_WASHDATA_EVENT,
)
from custom_components.washreminder.coordinator import WashReminderCoordinator


def _base_config(
    *,
    trigger_mode: str = TRIGGER_MODE_BINARY_SENSOR,
    trigger_entity: str = "binary_sensor.wm",
    trigger_state: str = "",
    door_sensor: str = "",
    door_inverted: bool = False,
    washdata_entry_id: str = "",
) -> dict:
    """Build a minimal config entry data dict."""
    data = {
        CONF_TRIGGER_MODE: trigger_mode,
        CONF_TRIGGER_ENTITY: trigger_entity,
        CONF_TRIGGER_STATE: trigger_state,
        CONF_PERSON: "person.someone",
        CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
        CONF_SNOOZE_MINUTES: 1,
        CONF_REPEAT_INTERVAL_MINUTES: 5,
        CONF_MAX_REPEATS: 3,
        CONF_ARRIVAL_DELAY_SECONDS: 0,
    }
    if door_sensor:
        data[CONF_DOOR_SENSOR] = door_sensor
        data[CONF_DOOR_SENSOR_INVERTED] = door_inverted
    if washdata_entry_id:
        data[CONF_WASHDATA_ENTRY_ID] = washdata_entry_id
    return data


def _mock_entry(hass: HomeAssistant, data: dict) -> MockConfigEntry:
    """Create a MockConfigEntry in LOADED state so lifecycle methods work."""
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


def _register_notify(hass: HomeAssistant) -> None:
    """Register a dummy notify service."""
    hass.services.async_register("notify", "mobile_app_phone", AsyncMock())


async def _setup_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry
) -> WashReminderCoordinator:
    """Instantiate and set up a coordinator with Store mocked."""
    coordinator = WashReminderCoordinator(hass, entry)
    with patch.object(coordinator._store, "async_load", return_value=None), \
         patch.object(coordinator._store, "async_save", return_value=None):
        await coordinator.async_setup()
    # Keep save mocked for background tasks during the test
    coordinator._store.async_save = AsyncMock()
    return coordinator


# ---------------------------------------------------------------------------
# Setup and entity validation
# ---------------------------------------------------------------------------


async def test_setup_raises_if_trigger_entity_missing(
    hass: HomeAssistant,
) -> None:
    """ConfigEntryNotReady if the trigger entity doesn't exist."""
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)

    with pytest.raises(ConfigEntryNotReady):
        coordinator = WashReminderCoordinator(hass, entry)
        await coordinator.async_setup()


async def test_setup_raises_if_person_entity_missing(
    hass: HomeAssistant,
) -> None:
    """ConfigEntryNotReady if the person entity doesn't exist."""
    hass.states.async_set("binary_sensor.wm", "off")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)

    with pytest.raises(ConfigEntryNotReady):
        coordinator = WashReminderCoordinator(hass, entry)
        await coordinator.async_setup()


async def test_setup_raises_if_door_sensor_missing(
    hass: HomeAssistant,
) -> None:
    """ConfigEntryNotReady if the configured door sensor doesn't exist."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(door_sensor="binary_sensor.door")
    entry = _mock_entry(hass, data)

    with pytest.raises(ConfigEntryNotReady):
        coordinator = WashReminderCoordinator(hass, entry)
        await coordinator.async_setup()


async def test_setup_succeeds_with_valid_entities(
    hass: HomeAssistant,
) -> None:
    """Coordinator sets up cleanly when all entities exist."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    assert coordinator.activity_state == "idle"
    assert coordinator.runtime_state == "idle"
    assert coordinator.pending is False


# ---------------------------------------------------------------------------
# Binary sensor trigger: on→off fires notification
# ---------------------------------------------------------------------------


async def test_binary_sensor_cycle_triggers_notification(
    hass: HomeAssistant,
) -> None:
    """on→off transition on binary sensor should start notification loop."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    assert coordinator.activity_state == "idle"

    # Simulate on→off transition
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is True
    assert coordinator.activity_state == "reminding"


async def test_binary_sensor_off_to_on_does_not_trigger(
    hass: HomeAssistant,
) -> None:
    """off→on should NOT trigger a notification."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.states.async_set("binary_sensor.wm", "on")
    await hass.async_block_till_done()

    assert coordinator.activity_state == "idle"


# ---------------------------------------------------------------------------
# State sensor trigger
# ---------------------------------------------------------------------------


async def test_state_sensor_triggers_on_configured_state(
    hass: HomeAssistant,
) -> None:
    """Transition to configured state should trigger notification."""
    hass.states.async_set("sensor.wm_state", "Running")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(
        trigger_mode=TRIGGER_MODE_STATE_SENSOR,
        trigger_entity="sensor.wm_state",
        trigger_state="Idle",
    )
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.states.async_set("sensor.wm_state", "Idle")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is True


async def test_state_sensor_ignores_unavailable_transition(
    hass: HomeAssistant,
) -> None:
    """unavailable→Idle should NOT trigger (startup guard)."""
    hass.states.async_set("sensor.wm_state", "unavailable")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(
        trigger_mode=TRIGGER_MODE_STATE_SENSOR,
        trigger_entity="sensor.wm_state",
        trigger_state="Idle",
    )
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.states.async_set("sensor.wm_state", "Idle")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is False


# ---------------------------------------------------------------------------
# WashData event trigger
# ---------------------------------------------------------------------------


async def test_washdata_event_triggers_notification(
    hass: HomeAssistant,
) -> None:
    """WashData cycle-ended event should trigger notification."""
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(
        trigger_mode=TRIGGER_MODE_WASHDATA_EVENT,
        trigger_entity="",
    )
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.bus.async_fire(EVENT_WASHDATA_CYCLE_ENDED, {"device_name": "WM"})
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is True


async def test_washdata_event_filtered_by_entry_id(
    hass: HomeAssistant,
) -> None:
    """WashData event with wrong entry_id should be ignored."""
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(
        trigger_mode=TRIGGER_MODE_WASHDATA_EVENT,
        trigger_entity="",
        washdata_entry_id="correct_id",
    )
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.bus.async_fire(
        EVENT_WASHDATA_CYCLE_ENDED,
        {"device_name": "WM", "entry_id": "wrong_id"},
    )
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is False
    assert coordinator.activity_state == "idle"


async def test_washdata_event_matching_entry_id_triggers(
    hass: HomeAssistant,
) -> None:
    """WashData event with correct entry_id should trigger."""
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config(
        trigger_mode=TRIGGER_MODE_WASHDATA_EVENT,
        trigger_entity="",
        washdata_entry_id="correct_id",
    )
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.bus.async_fire(
        EVENT_WASHDATA_CYCLE_ENDED,
        {"device_name": "WM", "entry_id": "correct_id"},
    )
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is True


# ---------------------------------------------------------------------------
# Person away → pending → arrival
# ---------------------------------------------------------------------------


async def test_person_away_sets_pending(
    hass: HomeAssistant,
) -> None:
    """Cycle completing while person is away should set pending."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "not_home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()

    assert coordinator.pending is True
    assert coordinator.person_listener_active is True
    assert coordinator.activity_state == "pending_arrival"


async def test_person_arrives_clears_pending_and_notifies(
    hass: HomeAssistant,
) -> None:
    """Person arriving home should clear pending and start delivery."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "not_home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle while away
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.pending is True

    # Person arrives (arrival_delay=0 so delivery starts immediately)
    hass.states.async_set("person.someone", "home")
    await hass.async_block_till_done()

    assert coordinator.pending is False
    assert coordinator.person_listener_active is False
    # Delivery task should be running (or notification loop started)
    assert coordinator.delivery_task_running or coordinator.notification_task_running


# ---------------------------------------------------------------------------
# Door sensor cancellation
# ---------------------------------------------------------------------------


async def test_door_open_cancels_notification_loop(
    hass: HomeAssistant,
) -> None:
    """Opening the door while reminding should cancel the loop."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    hass.states.async_set("binary_sensor.door", "off")
    _register_notify(hass)

    data = _base_config(door_sensor="binary_sensor.door")
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.notification_task_running is True

    # Open the door (on = open, default polarity)
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is False
    assert coordinator.activity_state == "idle"


async def test_door_open_clears_pending(
    hass: HomeAssistant,
) -> None:
    """Opening the door while pending should clear the pending flag."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "not_home")
    hass.states.async_set("binary_sensor.door", "off")
    _register_notify(hass)

    data = _base_config(door_sensor="binary_sensor.door")
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle while away
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.pending is True

    # Door opens
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()

    assert coordinator.pending is False
    assert coordinator.person_listener_active is False


async def test_door_inverted_polarity(
    hass: HomeAssistant,
) -> None:
    """Inverted door sensor: off = open should cancel loop."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    hass.states.async_set("binary_sensor.door", "on")
    _register_notify(hass)

    data = _base_config(door_sensor="binary_sensor.door", door_inverted=True)
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.notification_task_running is True

    # Door opens (off = open when inverted)
    hass.states.async_set("binary_sensor.door", "off")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is False


# ---------------------------------------------------------------------------
# Notification action handling
# ---------------------------------------------------------------------------


async def test_done_action_stops_loop(
    hass: HomeAssistant,
) -> None:
    """Tapping Done should stop the notification loop."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.notification_task_running is True

    # Give the notification loop a moment to reach _wait_for_action
    await asyncio.sleep(0.1)

    # Fire done action
    hass.bus.async_fire(EVENT_NOTIFICATION_ACTION, {"action": ACTION_DONE})
    await hass.async_block_till_done()
    await asyncio.sleep(0.1)

    assert coordinator.notification_task_running is False
    assert coordinator.activity_state == "idle"


# ---------------------------------------------------------------------------
# Coordinator properties
# ---------------------------------------------------------------------------


async def test_activity_state_transitions(
    hass: HomeAssistant,
) -> None:
    """activity_state should reflect the coordinator lifecycle."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    assert coordinator.activity_state == "idle"
    assert coordinator.runtime_state == "idle"


async def test_runtime_state_matches_activity(
    hass: HomeAssistant,
) -> None:
    """runtime_state should reflect task states correctly."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "not_home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger while away → pending → person listener active
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()

    assert coordinator.runtime_state == "awaiting_arrival"
    assert coordinator.pending is True


# ---------------------------------------------------------------------------
# Startup state restoration
# ---------------------------------------------------------------------------


async def test_startup_restores_pending_state(
    hass: HomeAssistant,
) -> None:
    """Coordinator should restore pending state from storage on startup."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "not_home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)

    coordinator = WashReminderCoordinator(hass, entry)
    with patch.object(coordinator._store, "async_load", return_value={"pending": True}), \
         patch.object(coordinator._store, "async_save", return_value=None):
        await coordinator.async_setup()

    assert coordinator.pending is True
    assert coordinator.person_listener_active is True


async def test_startup_pending_and_home_delivers(
    hass: HomeAssistant,
) -> None:
    """If pending on startup and person is home, should start delivery."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)

    coordinator = WashReminderCoordinator(hass, entry)
    with patch.object(coordinator._store, "async_load", return_value={"pending": True}), \
         patch.object(coordinator._store, "async_save", return_value=None):
        await coordinator.async_setup()

    # Keep save mocked for background delivery task
    coordinator._store.async_save = AsyncMock()

    # Should have cleared pending and started delivery
    assert coordinator.pending is False
    assert coordinator.delivery_task_running or coordinator.notification_task_running


# ---------------------------------------------------------------------------
# Door open clears notification after loop exhausted
# ---------------------------------------------------------------------------


async def test_door_open_clears_notification_after_loop_exhausted(
    hass: HomeAssistant,
) -> None:
    """Opening the door after the loop exhausted all repeats should still clear."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    hass.states.async_set("binary_sensor.door", "off")
    _register_notify(hass)

    data = _base_config(door_sensor="binary_sensor.door")
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Let the loop exhaust all repeats by making _wait_for_action always timeout
    with patch.object(
        coordinator, "_wait_for_action", new_callable=AsyncMock, return_value=None
    ):
        hass.states.async_set("binary_sensor.wm", "off")
        await hass.async_block_till_done()
        # Give the loop time to run through all iterations
        await asyncio.sleep(0.3)
        await hass.async_block_till_done()

    assert coordinator.notification_task_running is False

    # Spy on _clear_notification to verify door open triggers it
    with patch.object(
        coordinator, "_clear_notification", new_callable=AsyncMock
    ) as mock_clear:
        hass.states.async_set("binary_sensor.door", "on")
        await hass.async_block_till_done()
        await asyncio.sleep(0.1)
        await hass.async_block_till_done()

        mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# Person departure pauses reminders
# ---------------------------------------------------------------------------


async def test_person_leaves_pauses_reminder_loop(
    hass: HomeAssistant,
) -> None:
    """Person leaving home while reminding should pause the loop."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle — loop starts
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.notification_task_running is True

    # Person leaves home
    hass.states.async_set("person.someone", "not_home")
    await hass.async_block_till_done()

    assert coordinator.notification_task_running is False
    assert coordinator.pending is True
    assert coordinator.activity_state == "pending_arrival"


async def test_person_returns_resumes_after_pause(
    hass: HomeAssistant,
) -> None:
    """Person returning after departure-pause should resume reminders."""
    hass.states.async_set("binary_sensor.wm", "on")
    hass.states.async_set("person.someone", "home")
    _register_notify(hass)

    data = _base_config()
    entry = _mock_entry(hass, data)
    coordinator = await _setup_coordinator(hass, entry)

    # Trigger cycle — loop starts
    hass.states.async_set("binary_sensor.wm", "off")
    await hass.async_block_till_done()
    assert coordinator.notification_task_running is True

    # Person leaves home — loop pauses
    hass.states.async_set("person.someone", "not_home")
    await hass.async_block_till_done()
    assert coordinator.pending is True

    # Person returns home — should resume
    hass.states.async_set("person.someone", "home")
    await hass.async_block_till_done()

    assert coordinator.pending is False
    assert coordinator.delivery_task_running or coordinator.notification_task_running
