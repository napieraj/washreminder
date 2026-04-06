"""Wash Reminder coordinator — owns the full notification lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    ACTION_DONE,
    ACTION_SNOOZE,
    CONF_ARRIVAL_DELAY_SECONDS,
    CONF_CRITICAL_NOTIFICATION,
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
    DEFAULT_ARRIVAL_DELAY_SECONDS,
    DEFAULT_CRITICAL_NOTIFICATION,
    DEFAULT_MAX_REPEATS,
    DEFAULT_REPEAT_INTERVAL_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    DOMAIN,
    EVENT_WASHDATA_CYCLE_ENDED,
    NOTIFICATION_TAG,
    STORAGE_KEY,
    STORAGE_VERSION,
    TRIGGER_MODE_BINARY_SENSOR,
    TRIGGER_MODE_STATE_SENSOR,
    TRIGGER_MODE_WASHDATA_EVENT,
)

_LOGGER = logging.getLogger(__name__)

# States that indicate the sensor has never been in a real cycle —
# transitions FROM these states do not count as a cycle completion.
_NON_CYCLE_STATES: frozenset[str] = frozenset(
    {STATE_UNAVAILABLE, STATE_UNKNOWN, ""}
)


class WashReminderCoordinator:
    """Owns the full washer notification lifecycle.

    Trigger strategy
    ----------------
    Two modes, selected at config-flow time:

    Binary sensor (recommended, default):
        Watches binary_sensor.washing_machine_running for on→off.
        The binary sensor is debounced by WashData, so brief power glitches
        during a soak phase don't produce false triggers. This is the
        lowest-overhead option: only two state-change events per cycle.
        Chosen when the trigger entity ID is in the binary_sensor domain.

    State sensor:
        Watches sensor.washing_machine_state for a transition TO a
        user-specified value (e.g. "Idle"). Guarded so that the
        HA-startup unavailable→Idle transition does NOT trigger a
        notification. Useful if the binary sensor isn't available or
        you want finer-grained control (e.g. trigger on "Anti-Wrinkle").

    Door contact sensor (optional):
        Watches a binary_sensor on the machine door. When the door opens,
        any active notification loop is cancelled and the pending flag is
        cleared. The open state is "on" by default (HA convention), but
        can be inverted to "off" via the config flow for sensors with
        non-standard polarity. Always-active listener.

    IO minimisation
    ---------------
    When no wash cycle is in progress, only the trigger entity listener and
    (if configured) the door sensor listener are active. The person entity
    listener is subscribed dynamically — only when _pending=True — and torn
    down immediately on arrival or delivery.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

        # Options override data — lets the options flow reconfigure timing
        # parameters without touching the immutable config-flow data.
        config: dict[str, Any] = {**entry.data, **entry.options}

        self._trigger_entity: str = config.get(CONF_TRIGGER_ENTITY, "")
        self._trigger_state: str = config.get(CONF_TRIGGER_STATE, "")

        # Determine trigger mode — explicit from config, with backwards-compat
        # inference for entries created before the trigger_mode field existed.
        stored_mode = config.get(CONF_TRIGGER_MODE, "")
        if stored_mode:
            self._trigger_mode_value: str = stored_mode
        elif self._trigger_entity.startswith("binary_sensor."):
            self._trigger_mode_value = TRIGGER_MODE_BINARY_SENSOR
        elif self._trigger_entity:
            self._trigger_mode_value = TRIGGER_MODE_STATE_SENSOR
        else:
            self._trigger_mode_value = TRIGGER_MODE_WASHDATA_EVENT

        self._is_binary_sensor: bool = (
            self._trigger_mode_value == TRIGGER_MODE_BINARY_SENSOR
        )
        self._is_washdata_event: bool = (
            self._trigger_mode_value == TRIGGER_MODE_WASHDATA_EVENT
        )
        self._washdata_entry_id: str = config.get(CONF_WASHDATA_ENTRY_ID, "")

        self._person: str = config[CONF_PERSON]

        notify_full: str = config[CONF_NOTIFY_TARGET]
        self._notify_service: str = (
            notify_full[len("notify."):] if notify_full.startswith("notify.") else notify_full
        )

        # Optional door contact sensor — empty string means not configured.
        self._door_sensor: str = config.get(CONF_DOOR_SENSOR, "")
        # Polarity: HA device_class=door uses on=open by default.
        # Inverted sensors report off=open (e.g. some Zigbee contact sensors).
        self._door_open_state: str = (
            "off" if config.get(CONF_DOOR_SENSOR_INVERTED, False) else "on"
        )

        self._snooze_seconds: int = (
            int(config.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES)) * 60
        )
        self._repeat_interval_seconds: int = (
            int(config.get(CONF_REPEAT_INTERVAL_MINUTES, DEFAULT_REPEAT_INTERVAL_MINUTES)) * 60
        )
        self._max_repeats: int = int(config.get(CONF_MAX_REPEATS, DEFAULT_MAX_REPEATS))
        self._arrival_delay_seconds: int = int(
            config.get(CONF_ARRIVAL_DELAY_SECONDS, DEFAULT_ARRIVAL_DELAY_SECONDS)
        )
        self._critical_notification: bool = bool(
            config.get(CONF_CRITICAL_NOTIFICATION, DEFAULT_CRITICAL_NOTIFICATION)
        )

        # serialize_in_event_loop=True: explicit, matches the 2025.11+ default.
        self._store: Store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            serialize_in_event_loop=True,
        )

        # In-memory pending flag. Set synchronously in @callback handlers to
        # prevent race conditions on rapid consecutive state-change events.
        self._pending: bool = False

        # Dynamic person listener — only active while _pending=True.
        self._unsub_person: Callable[[], None] | None = None

        # Task tracking for restart-semantics cancellation.
        self._notification_task: asyncio.Task | None = None
        self._delivery_task: asyncio.Task | None = None

        # Loaded once during async_setup; cached for notification messages.
        self._translations: dict[str, str] = {}

        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Public properties — used by diagnostics.py and externally
    # ------------------------------------------------------------------

    @property
    def entry(self) -> ConfigEntry:
        """Config entry owning this coordinator."""
        return self._entry

    @property
    def activity_state(self) -> str:
        """Short state label for the diagnostic activity sensor."""
        if self.notification_task_running:
            return "reminding"
        if self.delivery_task_running:
            return "awaiting_delivery"
        if self._pending:
            return "pending_arrival"
        return "idle"

    @property
    def trigger_entity(self) -> str:
        """Return the trigger entity ID."""
        return self._trigger_entity or "(washdata event)"

    @property
    def trigger_mode(self) -> str:
        """Return 'binary_sensor', 'state_sensor', or 'washdata_event'."""
        return self._trigger_mode_value

    @property
    def trigger_state_display(self) -> str:
        """Return the trigger state value for display purposes."""
        if self._is_washdata_event:
            return "ha_washdata_cycle_ended event"
        return "on→off" if self._is_binary_sensor else self._trigger_state

    @property
    def door_sensor(self) -> str:
        """Return the door sensor entity ID (empty if not configured)."""
        return self._door_sensor

    @property
    def door_sensor_open_state(self) -> str:
        """Return the state value that means the door is open."""
        return self._door_open_state

    @property
    def pending(self) -> bool:
        """Return whether a deferred notification is pending."""
        return self._pending

    @property
    def person_listener_active(self) -> bool:
        """Return whether the person entity listener is currently subscribed."""
        return self._unsub_person is not None

    @property
    def notification_task_running(self) -> bool:
        """Return whether a notification loop task is currently in-flight."""
        return (
            self._notification_task is not None
            and not self._notification_task.done()
        )

    @property
    def delivery_task_running(self) -> bool:
        """Return whether an arrival delivery task is currently in-flight."""
        return (
            self._delivery_task is not None
            and not self._delivery_task.done()
        )

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked when entity-visible coordinator state changes."""
        self._listeners.append(update_callback)

        def remove() -> None:
            try:
                self._listeners.remove(update_callback)
            except ValueError:
                pass

        return remove

    @callback
    def async_update_listeners(self) -> None:
        """Notify all platform entities to refresh their state."""
        for listener in list(self._listeners):
            listener()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Validate entities, load persisted state, load translations, register listeners."""

        # Validate trigger entity (entity modes only — washdata event mode
        # has no entity to validate).
        if not self._is_washdata_event:
            trigger_state = self._hass.states.get(self._trigger_entity)
            if trigger_state is None:
                raise ConfigEntryNotReady(
                    translation_domain=DOMAIN,
                    translation_key="trigger_entity_not_found",
                    translation_placeholders={"entity": self._trigger_entity},
                )

        if self._hass.states.get(self._person) is None:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="person_entity_not_found",
                translation_placeholders={"entity": self._person},
            )

        if self._door_sensor and self._hass.states.get(self._door_sensor) is None:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="door_sensor_not_found",
                translation_placeholders={"entity": self._door_sensor},
            )

        # Load notification message translations from the integration's own
        # translations directory. HA's async_get_translations only supports
        # built-in categories (config, options, exceptions), not custom ones
        # like "notify", so we load the JSON directly.
        self._translations = await self._hass.async_add_executor_job(
            self._load_notify_translations
        )

        stored = await self._store.async_load()
        if stored:
            self._pending = stored.get("pending", False)
            _LOGGER.debug("Restored pending state: %s", self._pending)

        # Trigger listener: always active, minimal IO when idle.
        if self._is_washdata_event:
            self._entry.async_on_unload(
                self._hass.bus.async_listen(
                    EVENT_WASHDATA_CYCLE_ENDED, self._on_washdata_cycle_ended
                )
            )
        else:
            self._entry.async_on_unload(
                async_track_state_change_event(
                    self._hass, self._trigger_entity, self._on_trigger_state_change
                )
            )

        # Door contact sensor listener: always active (if configured).
        if self._door_sensor:
            self._entry.async_on_unload(
                async_track_state_change_event(
                    self._hass, self._door_sensor, self._on_door_state_change
                )
            )

        # Person listener cleanup guard — covers HA unload while pending + away.
        self._entry.async_on_unload(self._unsubscribe_person)

        # Restore state after HA restart.
        if self._pending:
            person_state = self._hass.states.get(self._person)
            if person_state and person_state.state == "home":
                _LOGGER.debug("Startup: pending and already home — notifying now")
                self._pending = False
                self._delivery_task = self._entry.async_create_background_task(
                    self._hass,
                    self._deliver_on_arrival(),
                    name="washreminder_startup_delivery",
                )
            else:
                self._subscribe_person()

        self.async_update_listeners()

    # ------------------------------------------------------------------
    # Dynamic person listener management
    # ------------------------------------------------------------------

    def _subscribe_person(self) -> None:
        """Subscribe to person state changes. No-op if already subscribed."""
        if self._unsub_person is not None:
            return
        self._unsub_person = async_track_state_change_event(
            self._hass, self._person, self._on_person_state_change
        )
        _LOGGER.debug("Listening for %s to arrive home", self._person)
        self.async_update_listeners()

    def _unsubscribe_person(self) -> None:
        """Unsubscribe from person state changes. Idempotent."""
        if self._unsub_person is not None:
            self._unsub_person()
            self._unsub_person = None
            _LOGGER.debug("Stopped listening for %s", self._person)
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------

    def _load_notify_translations(self) -> dict[str, str]:
        """Load the 'notify' section from the integration's translation files.

        Runs in the executor (blocking I/O). Tries the user's configured HA
        language first, falls back to English, falls back to empty dict.
        """
        translations_dir = Path(__file__).parent / "translations"
        language = self._hass.config.language

        for lang in dict.fromkeys((language, "en")):
            path = translations_dir / f"notify_{lang}.json"
            if path.is_file():
                try:
                    notify = json.loads(path.read_text(encoding="utf-8"))
                    if notify:
                        _LOGGER.debug("Loaded notification text from %s", path.name)
                        return notify
                except (json.JSONDecodeError, OSError):
                    _LOGGER.debug("Could not parse %s", path)

        _LOGGER.debug("No translations found, using defaults")
        return {}

    def _t(self, key: str, **kwargs: str) -> str:
        """Look up a notification translation string with placeholder substitution.

        Falls back to the key itself if not found — ensures notifications
        are always sent even if translations fail to load.
        """
        template = self._translations.get(key, key)
        if kwargs:
            for placeholder, value in kwargs.items():
                template = template.replace(f"{{{placeholder}}}", value)
        return template

    # ------------------------------------------------------------------
    # State change handlers — synchronous @callback, event-loop context
    # ------------------------------------------------------------------

    @callback
    def _handle_cycle_complete(self) -> None:
        """Common logic for all trigger modes when a cycle finishes."""
        self._cancel_delivery_task()

        person_state = self._hass.states.get(self._person)
        if person_state and person_state.state == "home":
            _LOGGER.debug("Person is home — sending reminder now")
            self._start_loop()
        else:
            _LOGGER.debug("Person is away — saving pending state, will notify on arrival")
            self._pending = True
            self._subscribe_person()
            self._entry.async_create_background_task(
                self._hass,
                self._persist_pending(True),
                name="washreminder_set_pending",
            )

        self.async_update_listeners()

    @callback
    def _on_trigger_state_change(self, event: Event) -> None:
        """Handle washer trigger entity state changes."""
        old = event.data.get("old_state")
        new = event.data.get("new_state")

        if not old or not new:
            return

        cycle_complete = False

        if self._is_binary_sensor:
            cycle_complete = old.state == "on" and new.state == "off"
        else:
            cycle_complete = (
                new.state == self._trigger_state
                and old.state not in _NON_CYCLE_STATES
                and old.state != self._trigger_state
            )

        if not cycle_complete:
            return

        _LOGGER.debug(
            "Cycle finished: %s changed from %s to %s",
            self._trigger_entity,
            old.state,
            new.state,
        )

        self._handle_cycle_complete()

    @callback
    def _on_washdata_cycle_ended(self, event: Event) -> None:
        """Handle ha_washdata_cycle_ended events from the event bus."""
        if self._washdata_entry_id:
            if event.data.get("entry_id") != self._washdata_entry_id:
                return

        _LOGGER.debug(
            "WashData cycle ended: device=%s, program=%s",
            event.data.get("device_name", "unknown"),
            event.data.get("program", "unknown"),
        )

        self._handle_cycle_complete()

    @callback
    def _on_person_state_change(self, event: Event) -> None:
        """Handle person entity state changes — only active while _pending=True."""
        old = event.data.get("old_state")
        new = event.data.get("new_state")

        if not (old and old.state != "home" and new and new.state == "home"):
            return

        if not self._pending:
            self._unsubscribe_person()
            return

        self._pending = False
        self._unsubscribe_person()

        _LOGGER.debug("Person arrived home — sending pending reminder")
        self._delivery_task = self._entry.async_create_background_task(
            self._hass,
            self._deliver_on_arrival(),
            name="washreminder_arrival_delivery",
        )

        self.async_update_listeners()

    @callback
    def _on_door_state_change(self, event: Event) -> None:
        """Handle door contact sensor — cancel everything when door opens.

        The open state is configurable via the inverted toggle:
        - Standard (default): on = open, off = closed
        - Inverted: off = open, on = closed
        """
        new = event.data.get("new_state")
        if not new or new.state != self._door_open_state:
            return

        actions_taken: list[str] = []

        # Cancel active notification loop.
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
            self._notification_task = None
            self._entry.async_create_background_task(
                self._hass,
                self._clear_notification(),
                name="washreminder_door_clear_notification",
            )
            actions_taken.append("stopped reminder loop")

        # Cancel in-flight delivery task (WiFi delay in progress).
        if self._delivery_task and not self._delivery_task.done():
            self._delivery_task.cancel()
            self._delivery_task = None
            actions_taken.append("cancelled arrival delivery")

        # Clear pending flag if set (person was away, door opened somehow).
        if self._pending:
            self._pending = False
            self._unsubscribe_person()
            self._entry.async_create_background_task(
                self._hass,
                self._persist_pending(False),
                name="washreminder_door_clear_pending",
            )
            actions_taken.append("cleared pending state")

        if actions_taken:
            _LOGGER.info("Door opened — %s", ", ".join(actions_taken))
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # Loop management
    # ------------------------------------------------------------------

    def _start_loop(self) -> None:
        """Cancel any in-flight loop (restart semantics) and start a fresh one.

        Uses entry.async_create_background_task so the task auto-cancels on
        entry unload. We track _notification_task for restart-cancel only.
        """
        if self._notification_task and not self._notification_task.done():
            _LOGGER.debug("Cancelling previous reminder loop")
            self._notification_task.cancel()

        self._notification_task = self._entry.async_create_background_task(
            self._hass,
            self._notification_loop(),
            name="washreminder_notification_loop",
        )
        self.async_update_listeners()

    def _cancel_delivery_task(self) -> None:
        """Cancel an in-flight delivery task if one exists."""
        if self._delivery_task and not self._delivery_task.done():
            _LOGGER.debug("Cancelling pending arrival delivery")
            self._delivery_task.cancel()
            self._delivery_task = None
            self.async_update_listeners()

    async def _deliver_on_arrival(self) -> None:
        """Persist cleared pending flag, wait for WiFi handshake, then start loop."""
        await self._persist_pending(False)
        self.async_update_listeners()
        _LOGGER.debug(
            "Waiting %ds for WiFi reconnect before sending reminder",
            self._arrival_delay_seconds,
        )
        await asyncio.sleep(self._arrival_delay_seconds)
        self._start_loop()

    # ------------------------------------------------------------------
    # Notification loop
    # ------------------------------------------------------------------

    async def _notification_loop(self) -> None:
        self.async_update_listeners()
        try:
            for i in range(self._max_repeats):
                message = (
                    self._t("cycle_complete")
                    if i == 0
                    else self._t("reminder_escalation", count=str(i + 1))
                )

                extra: dict[str, Any] = {
                    "tag": NOTIFICATION_TAG,
                    "actions": [
                        {"action": ACTION_SNOOZE, "title": self._t("action_snooze")},
                        {"action": ACTION_DONE, "title": self._t("action_done")},
                    ],
                }
                if self._critical_notification:
                    extra["push"] = {"interruption-level": "time-sensitive"}

                try:
                    await self._notify(
                        title=self._t("title"),
                        message=message,
                        extra=extra,
                    )
                except HomeAssistantError:
                    _LOGGER.error(
                        "Could not send notification via notify.%s — stopping reminders",
                        self._notify_service,
                    )
                    self.async_update_listeners()
                    return

                self.async_update_listeners()

                result = await self._wait_for_action(
                    {ACTION_SNOOZE, ACTION_DONE},
                    timeout=self._repeat_interval_seconds,
                )

                if result == ACTION_DONE:
                    await self._clear_notification()
                    _LOGGER.info("Reminder acknowledged")
                    self.async_update_listeners()
                    return

                if result == ACTION_SNOOZE:
                    await self._clear_notification()
                    _LOGGER.debug("Snoozed — next reminder in %ds", self._snooze_seconds)
                    await asyncio.sleep(self._snooze_seconds)
                    # Loop continues — sends fresh notification
                else:
                    _LOGGER.debug(
                        "No response after %ds — sending reminder %d of %d",
                        self._repeat_interval_seconds,
                        i + 1,
                        self._max_repeats,
                    )

            _LOGGER.info("Reached %d reminders — stopping", self._max_repeats)

        except asyncio.CancelledError:
            _LOGGER.debug("Reminder loop cancelled")
            raise  # Must re-raise; asyncio task machinery depends on this
        finally:
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _wait_for_action(self, actions: set[str], timeout: float) -> str | None:
        """Block until a mobile_app_notification_action event fires matching
        one of the given action identifiers, or until timeout elapses.

        The event bus listener is scoped to this call — it is torn down in
        the finally block including on CancelledError, so no orphaned
        listeners accumulate during rapid cycle restarts.
        """
        trigger_event = asyncio.Event()
        matched: list[str] = []

        @callback
        def _handler(event: Event) -> None:
            action = event.data.get("action", "")
            if action in actions and not trigger_event.is_set():
                matched.append(action)
                trigger_event.set()

        unsub = self._hass.bus.async_listen("mobile_app_notification_action", _handler)
        try:
            await asyncio.wait_for(trigger_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            unsub()

        return matched[0] if matched else None

    async def _notify(self, title: str, message: str, extra: dict) -> None:
        """Invoke the legacy notify service.

        Raises HomeAssistantError on failure so the caller can decide
        whether to abort or retry.
        """
        await self._hass.services.async_call(
            "notify",
            self._notify_service,
            {"title": title, "message": message, "data": extra},
        )

    async def _clear_notification(self) -> None:
        """Clear the notification from the device using the tag."""
        try:
            await self._hass.services.async_call(
                "notify",
                self._notify_service,
                {"message": "clear_notification", "data": {"tag": NOTIFICATION_TAG}},
            )
        except HomeAssistantError:
            _LOGGER.debug("Could not clear notification from device")

    async def _persist_pending(self, value: bool) -> None:
        """Async store write. Only called from background tasks."""
        await self._store.async_save({"pending": value})
        _LOGGER.debug("Saved pending state: %s", value)
