"""Config flow for Wash Reminder."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ARRIVAL_DELAY_SECONDS,
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_INVERTED,
    CONF_MAX_REPEATS,
    CONF_NOTIFY_TARGET,
    CONF_PERSON,
    CONF_REPEAT_INTERVAL_MINUTES,
    CONF_SNOOZE_MINUTES,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STATE,
    DEFAULT_ARRIVAL_DELAY_SECONDS,
    DEFAULT_BINARY_SENSOR_TRIGGER_STATE,
    DEFAULT_MAX_REPEATS,
    DEFAULT_REPEAT_INTERVAL_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    DOMAIN,
)


def _entity_schema(defaults: dict) -> vol.Schema:
    """Build the entity configuration schema.

    Both binary_sensor and sensor domains are accepted for the trigger entity.
    Leave trigger_state blank to use binary-sensor on→off logic; enter a value
    like "Idle" to use state-sensor completion-value logic.
    """
    schema: dict = {
        vol.Required(
            CONF_TRIGGER_ENTITY,
            default=defaults.get(CONF_TRIGGER_ENTITY, ""),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
        ),
        vol.Optional(
            CONF_TRIGGER_STATE,
            default=defaults.get(CONF_TRIGGER_STATE, DEFAULT_BINARY_SENSOR_TRIGGER_STATE),
        ): selector.TextSelector(),
        vol.Required(
            CONF_PERSON,
            default=defaults.get(CONF_PERSON, ""),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="person")
        ),
        vol.Required(
            CONF_NOTIFY_TARGET,
            default=defaults.get(CONF_NOTIFY_TARGET, ""),
        ): selector.TextSelector(),
    }

    # Door sensor: vol.Optional without default so HA omits the key entirely
    # when nothing is selected. The coordinator treats absent/empty as
    # "not configured". When reconfiguring with an existing sensor, the
    # current value is passed via suggested_value so the picker pre-fills.
    door_default = defaults.get(CONF_DOOR_SENSOR)
    if door_default:
        schema[vol.Optional(
            CONF_DOOR_SENSOR,
            description={"suggested_value": door_default},
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        )
    else:
        schema[vol.Optional(CONF_DOOR_SENSOR)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        )

    # Inverted toggle: only meaningful when a door sensor is configured,
    # but HA config flows don't support conditional fields. The description
    # makes it clear this only applies to the door sensor.
    schema[vol.Optional(
        CONF_DOOR_SENSOR_INVERTED,
        default=defaults.get(CONF_DOOR_SENSOR_INVERTED, False),
    )] = selector.BooleanSelector()

    return vol.Schema(schema)


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
                default=int(defaults.get(CONF_REPEAT_INTERVAL_MINUTES, DEFAULT_REPEAT_INTERVAL_MINUTES)),
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
                default=int(defaults.get(CONF_ARRIVAL_DELAY_SECONDS, DEFAULT_ARRIVAL_DELAY_SECONDS)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=120, step=5, mode="box")
            ),
        }
    )


def _normalise_notify_target(user_input: dict) -> dict:
    """Ensure notify_target has exactly one notify. prefix."""
    target = user_input.get(CONF_NOTIFY_TARGET, "").strip()
    # Strip all leading "notify." prefixes to handle double-prefix typos.
    while target.startswith("notify."):
        target = target[len("notify."):]
    if target:
        user_input[CONF_NOTIFY_TARGET] = f"notify.{target}"
    return user_input


def _validate_notify_service(
    hass: HomeAssistant, user_input: dict
) -> dict[str, str]:
    """Check the notify service exists. Returns errors dict."""
    errors: dict[str, str] = {}
    notify_target = user_input.get(CONF_NOTIFY_TARGET, "")
    if notify_target:
        service_name = (
            notify_target[len("notify."):]
            if notify_target.startswith("notify.")
            else notify_target
        )
        if not hass.services.has_service("notify", service_name):
            errors[CONF_NOTIFY_TARGET] = "notify_service_not_found"
    return errors


class WashReminderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Wash Reminder.

    Entity configuration (trigger, person, notify target, door sensor) is
    handled here and in the reconfiguration flow. Timing parameters are in
    the options flow — no reinstall needed to adjust them.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._entity_data: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1 of 2: entity configuration."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalise_notify_target(user_input)
            errors = _validate_notify_service(self.hass, user_input)
            errors |= _validate_trigger_state_for_sensor(user_input)

            if not errors:
                self._entity_data = user_input
                return await self.async_step_timing()

        return self.async_show_form(
            step_id="user",
            data_schema=_entity_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_timing(self, user_input=None):
        """Step 2 of 2: timing configuration."""
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
        """Reconfigure entity settings without removing the integration.

        Timing parameters are in the options flow — only entity fields here.
        Silver quality-scale requirement: reconfiguration-flow.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalise_notify_target(user_input)
            errors = _validate_notify_service(self.hass, user_input)
            errors |= _validate_trigger_state_for_sensor(user_input)

            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=user_input,
                )

        current = dict(self._get_reconfigure_entry().data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_entity_schema(current),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WashReminderOptionsFlow:
        return WashReminderOptionsFlow()


class WashReminderOptionsFlow(config_entries.OptionsFlow):
    """Options flow for adjusting timing parameters post-setup.

    Changes trigger a coordinator reload via _async_reload_on_update (registered
    in async_setup_entry). The coordinator merges {**entry.data, **entry.options}
    so options values override without touching the immutable config data.
    """

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_timing_schema(current),
        )
