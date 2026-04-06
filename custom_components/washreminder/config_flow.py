"""Config flow for Wash Reminder."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_BINARY_SENSOR_TRIGGER_STATE,
    DEFAULT_CRITICAL_NOTIFICATION,
    DEFAULT_MAX_REPEATS,
    DEFAULT_REPEAT_INTERVAL_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    DOMAIN,
    TRIGGER_MODE_BINARY_SENSOR,
    TRIGGER_MODE_STATE_SENSOR,
    TRIGGER_MODE_WASHDATA_EVENT,
    WASHDATA_DOMAIN,
)


def _trigger_mode_schema(defaults: dict) -> vol.Schema:
    """Schema for the trigger mode selection step."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TRIGGER_MODE,
                default=defaults.get(CONF_TRIGGER_MODE, TRIGGER_MODE_WASHDATA_EVENT),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=TRIGGER_MODE_WASHDATA_EVENT,
                            label="WashData event (automatic)",
                        ),
                        selector.SelectOptionDict(
                            value="manual",
                            label="Manual entity selection",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _washdata_device_schema(
    hass: HomeAssistant, defaults: dict
) -> vol.Schema:
    """Schema for the WashData device selection step."""
    entries = hass.config_entries.async_entries(WASHDATA_DOMAIN)

    options: list[selector.SelectOptionDict] = [
        selector.SelectOptionDict(value="", label="All devices"),
    ]
    options.extend(
        selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
        for entry in entries
    )

    # Pre-select: if one device exists, default to it; otherwise "All devices".
    default = defaults.get(CONF_WASHDATA_ENTRY_ID, "")
    if not default and len(entries) == 1:
        default = entries[0].entry_id

    return vol.Schema(
        {
            vol.Optional(
                CONF_WASHDATA_ENTRY_ID,
                default=default,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _pick_trigger_schema(defaults: dict) -> vol.Schema:
    """Schema for the cycle-completion entity step."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TRIGGER_ENTITY,
                default=defaults.get(CONF_TRIGGER_ENTITY, ""),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
            ),
        }
    )


def _trigger_state_schema(defaults: dict) -> vol.Schema:
    """Schema for state-sensor completion value."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TRIGGER_STATE,
                default=defaults.get(
                    CONF_TRIGGER_STATE, DEFAULT_BINARY_SENSOR_TRIGGER_STATE
                ),
            ): selector.TextSelector(),
        }
    )


def _presence_notify_door_schema(
    hass: HomeAssistant, defaults: dict
) -> vol.Schema:
    """Person, notify entity, optional door sensor."""
    door_default = defaults.get(CONF_DOOR_SENSOR)
    if door_default:
        door_key = vol.Optional(
            CONF_DOOR_SENSOR,
            description={"suggested_value": door_default},
        )
    else:
        door_key = vol.Optional(CONF_DOOR_SENSOR)

    # Build notify options from registered services so that targets without
    # entity-registry entries (e.g. iOS Companion App) still appear.
    notify_services = hass.services.async_services().get("notify", {})
    notify_options = sorted(
        [
            selector.SelectOptionDict(
                value=f"notify.{svc}", label=f"notify.{svc}"
            )
            for svc in notify_services
        ],
        key=lambda opt: opt["label"],
    )

    return vol.Schema(
        {
            vol.Required(
                CONF_PERSON,
                default=defaults.get(CONF_PERSON, ""),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="person")),
            vol.Required(
                CONF_NOTIFY_TARGET,
                default=defaults.get(CONF_NOTIFY_TARGET, ""),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            door_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
        }
    )


def _door_options_schema(defaults: dict) -> vol.Schema:
    """Invert toggle — only shown when a door sensor is configured."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_DOOR_SENSOR_INVERTED,
                default=defaults.get(CONF_DOOR_SENSOR_INVERTED, False),
            ): selector.BooleanSelector(),
        }
    )


def _validate_trigger_state_for_sensor(user_input: dict) -> dict[str, str]:
    """State sensors require a non-empty completion value (binary uses on→off)."""
    errors: dict[str, str] = {}
    entity_id = user_input.get(CONF_TRIGGER_ENTITY, "")
    raw_state = user_input.get(
        CONF_TRIGGER_STATE, DEFAULT_BINARY_SENSOR_TRIGGER_STATE
    )
    trigger_state = raw_state.strip() if isinstance(raw_state, str) else ""
    if entity_id.startswith("sensor.") and not trigger_state:
        errors[CONF_TRIGGER_STATE] = "trigger_state_required"
    return errors


def _timing_schema(defaults: dict) -> vol.Schema:
    """Build the timing configuration schema (used in both config and options flows)."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SNOOZE_MINUTES,
                default=int(defaults.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, mode="box")
            ),
            vol.Optional(
                CONF_REPEAT_INTERVAL_MINUTES,
                default=int(
                    defaults.get(
                        CONF_REPEAT_INTERVAL_MINUTES, DEFAULT_REPEAT_INTERVAL_MINUTES
                    )
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=120, step=5, mode="box")
            ),
            vol.Optional(
                CONF_MAX_REPEATS,
                default=int(defaults.get(CONF_MAX_REPEATS, DEFAULT_MAX_REPEATS)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=50, step=1, mode="box")
            ),
            vol.Optional(
                CONF_ARRIVAL_DELAY_SECONDS,
                default=int(
                    defaults.get(
                        CONF_ARRIVAL_DELAY_SECONDS, DEFAULT_ARRIVAL_DELAY_SECONDS
                    )
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=120, step=5, mode="box")
            ),
            vol.Optional(
                CONF_CRITICAL_NOTIFICATION,
                default=bool(
                    defaults.get(
                        CONF_CRITICAL_NOTIFICATION, DEFAULT_CRITICAL_NOTIFICATION
                    )
                ),
            ): selector.BooleanSelector(),
        }
    )


def _notify_service_name(entity_id: str) -> str:
    """Map notify entity_id to notify domain service name."""
    if not entity_id.startswith("notify."):
        return ""
    return entity_id.removeprefix("notify.")


def _validate_notify_target(
    hass: HomeAssistant, user_input: dict
) -> dict[str, str]:
    """Ensure the notify service is callable."""
    errors: dict[str, str] = {}
    entity_id = (user_input.get(CONF_NOTIFY_TARGET) or "").strip()
    if not entity_id:
        errors[CONF_NOTIFY_TARGET] = "notify_entity_required"
        return errors
    if not entity_id.startswith("notify."):
        errors[CONF_NOTIFY_TARGET] = "notify_entity_invalid"
        return errors

    service = _notify_service_name(entity_id)
    if not service or not hass.services.has_service("notify", service):
        errors[CONF_NOTIFY_TARGET] = "notify_service_not_found"
    return errors


def _normalise_door_fields(data: dict) -> dict:
    """Drop empty door sensor and clear invert when no door."""
    result = dict(data)
    door = result.get(CONF_DOOR_SENSOR)
    if not door or (isinstance(door, str) and not door.strip()):
        result.pop(CONF_DOOR_SENSOR, None)
        result[CONF_DOOR_SENSOR_INVERTED] = False
    return result


class WashReminderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Wash Reminder.

    Entity configuration uses multiple steps so optional fields only appear when
    relevant. Timing parameters are in the options flow.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._entity_data: dict = {}
        self._reconfigure_mode: bool = False

    async def async_step_user(self, user_input=None):
        """Start setup: pick trigger mode."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        self._reconfigure_mode = False
        if not self._entity_data:
            self._entity_data = {}

        return await self.async_step_trigger_mode(user_input)

    async def async_step_trigger_mode(self, user_input=None):
        """Choose between WashData event or manual entity selection."""
        if user_input is not None:
            mode = user_input[CONF_TRIGGER_MODE]
            if mode == TRIGGER_MODE_WASHDATA_EVENT:
                self._entity_data[CONF_TRIGGER_MODE] = TRIGGER_MODE_WASHDATA_EVENT
                self._entity_data.pop(CONF_TRIGGER_ENTITY, None)
                self._entity_data.pop(CONF_TRIGGER_STATE, None)
                return await self.async_step_washdata_device(None)
            # Manual mode — clear washdata fields, proceed to entity picker.
            self._entity_data.pop(CONF_WASHDATA_ENTRY_ID, None)
            return await self.async_step_pick_trigger(None)

        # Infer default for reconfigure: if entry already has a trigger mode,
        # use it; otherwise check for trigger_entity to decide.
        default_mode = self._entity_data.get(CONF_TRIGGER_MODE, "")
        if not default_mode and self._entity_data.get(CONF_TRIGGER_ENTITY):
            default_mode = "manual"
        defaults = {CONF_TRIGGER_MODE: default_mode} if default_mode else {}

        return self.async_show_form(
            step_id="trigger_mode",
            data_schema=_trigger_mode_schema(defaults),
        )

    async def async_step_washdata_device(self, user_input=None):
        """Select which WashData device triggers reminders."""
        if user_input is not None:
            self._entity_data[CONF_WASHDATA_ENTRY_ID] = user_input.get(
                CONF_WASHDATA_ENTRY_ID, ""
            )
            return await self.async_step_presence_notify_door(None)

        return self.async_show_form(
            step_id="washdata_device",
            data_schema=_washdata_device_schema(self.hass, self._entity_data),
        )

    async def async_step_pick_trigger(self, user_input=None):
        """Select binary_sensor or sensor for cycle completion."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_TRIGGER_ENTITY]
            self._entity_data[CONF_TRIGGER_ENTITY] = entity_id
            if entity_id.startswith("binary_sensor."):
                self._entity_data[CONF_TRIGGER_STATE] = ""
                self._entity_data[CONF_TRIGGER_MODE] = TRIGGER_MODE_BINARY_SENSOR
                return await self.async_step_presence_notify_door(None)
            self._entity_data[CONF_TRIGGER_MODE] = TRIGGER_MODE_STATE_SENSOR
            return await self.async_step_trigger_state(None)

        return self.async_show_form(
            step_id="pick_trigger",
            data_schema=_pick_trigger_schema(self._entity_data),
            errors=errors,
        )

    async def async_step_trigger_state(self, user_input=None):
        """Completion state for sensor.* triggers only."""
        errors: dict[str, str] = {}

        if user_input is not None:
            merged = {**self._entity_data, **user_input}
            errors = _validate_trigger_state_for_sensor(merged)
            if not errors:
                self._entity_data[CONF_TRIGGER_STATE] = user_input[
                    CONF_TRIGGER_STATE
                ].strip()
                return await self.async_step_presence_notify_door(None)

        return self.async_show_form(
            step_id="trigger_state",
            data_schema=_trigger_state_schema(self._entity_data),
            errors=errors,
        )

    async def async_step_presence_notify_door(self, user_input=None):
        """Person, notify entity, optional door sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_notify_target(self.hass, user_input)
            if not errors:
                self._entity_data.update(user_input)
                door = self._entity_data.get(CONF_DOOR_SENSOR)
                has_door = bool(door and str(door).strip())
                if not has_door:
                    self._entity_data.pop(CONF_DOOR_SENSOR, None)
                    self._entity_data[CONF_DOOR_SENSOR_INVERTED] = False
                    return await self._async_finish_entities_step()
                return await self.async_step_door_options(None)

        merged_defaults = {**self._entity_data, **(user_input or {})}
        return self.async_show_form(
            step_id="presence_notify_door",
            data_schema=_presence_notify_door_schema(self.hass, merged_defaults),
            errors=errors,
        )

    async def async_step_door_options(self, user_input=None):
        """Door sensor polarity — only after a door entity was chosen."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._entity_data[CONF_DOOR_SENSOR_INVERTED] = user_input.get(
                CONF_DOOR_SENSOR_INVERTED, False
            )
            return await self._async_finish_entities_step()

        return self.async_show_form(
            step_id="door_options",
            data_schema=_door_options_schema(self._entity_data),
            errors=errors,
        )

    async def _async_finish_entities_step(self):
        """Reconfigure ends here; new config continues to timing."""
        data = _normalise_door_fields(self._entity_data)
        if self._reconfigure_mode:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=data,
            )
        self._entity_data = data
        return await self.async_step_timing(None)

    async def async_step_timing(self, user_input=None):
        """Final setup step: timing parameters."""
        if user_input is not None:
            return self.async_create_entry(
                title="Wash Reminder",
                data={**self._entity_data, **user_input},
            )

        return self.async_show_form(
            step_id="timing",
            data_schema=_timing_schema({}),
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure entity settings (same steps as setup, without timing)."""
        if not self._reconfigure_mode:
            self._reconfigure_mode = True
            self._entity_data = dict(self._get_reconfigure_entry().data)

        return await self.async_step_trigger_mode(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WashReminderOptionsFlow:
        return WashReminderOptionsFlow()


class WashReminderOptionsFlow(config_entries.OptionsFlow):
    """Options flow for adjusting timing parameters post-setup."""

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_timing_schema(current),
        )
