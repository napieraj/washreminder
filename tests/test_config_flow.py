"""Tests for Wash Reminder config flow."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.washreminder.config_flow import (
    _validate_trigger_state_for_sensor,
)
from custom_components.washreminder.const import (
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_INVERTED,
    CONF_NOTIFY_TARGET,
    CONF_PERSON,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_MODE,
    CONF_TRIGGER_STATE,
    CONF_WASHDATA_ENTRY_ID,
    DOMAIN,
    TRIGGER_MODE_BINARY_SENSOR,
    TRIGGER_MODE_WASHDATA_EVENT,
)


def test_validate_trigger_binary_empty_state_ok() -> None:
    assert not _validate_trigger_state_for_sensor(
        {CONF_TRIGGER_ENTITY: "binary_sensor.wm", CONF_TRIGGER_STATE: ""}
    )


def test_validate_trigger_sensor_whitespace_state_errors() -> None:
    assert _validate_trigger_state_for_sensor(
        {CONF_TRIGGER_ENTITY: "sensor.wm_state", CONF_TRIGGER_STATE: "  "}
    ) == {CONF_TRIGGER_STATE: "trigger_state_required"}


def test_validate_trigger_sensor_with_state_ok() -> None:
    assert not _validate_trigger_state_for_sensor(
        {
            CONF_TRIGGER_ENTITY: "sensor.wm_state",
            CONF_TRIGGER_STATE: "Idle",
        }
    )


@pytest.fixture
def mock_setup_entry():
    """Avoid full coordinator setup when the flow creates an entry."""
    with patch(
        "custom_components.washreminder.async_setup_entry",
        new=AsyncMock(return_value=True),
    ) as mock:
        yield mock


def _register_notify_service(hass: HomeAssistant) -> None:
    """Register a notify service for tests (no entity registry entry needed)."""

    async def _dummy_notify(_call) -> None:
        return

    hass.services.async_register("notify", "mobile_app_phone", _dummy_notify)


async def _select_manual_trigger_mode(hass, flow_id):
    """Helper: select 'manual' in the trigger_mode step."""
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={CONF_TRIGGER_MODE: "manual"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pick_trigger"
    return result


async def test_config_flow_binary_through_timing(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    _register_notify_service(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "trigger_mode"

    result = await _select_manual_trigger_mode(hass, result["flow_id"])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_ENTITY: "binary_sensor.wm"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "presence_notify_door"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "timing"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wash Reminder"
    assert result["data"][CONF_TRIGGER_STATE] == ""
    assert result["data"][CONF_TRIGGER_MODE] == TRIGGER_MODE_BINARY_SENSOR
    mock_setup_entry.assert_called_once()


async def test_config_flow_sensor_requires_completion_state(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("sensor.wm_state", "Idle")
    hass.states.async_set("person.someone", "home")
    _register_notify_service(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await _select_manual_trigger_mode(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_ENTITY: "sensor.wm_state"},
    )
    assert result["step_id"] == "trigger_state"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_STATE: ""},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "trigger_state"
    assert result["errors"] == {CONF_TRIGGER_STATE: "trigger_state_required"}


async def test_config_flow_door_adds_options_step(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    hass.states.async_set("binary_sensor.door", "off")
    _register_notify_service(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await _select_manual_trigger_mode(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_ENTITY: "binary_sensor.wm"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
            CONF_DOOR_SENSOR: "binary_sensor.door",
        },
    )
    assert result["step_id"] == "door_options"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_DOOR_SENSOR_INVERTED: True},
    )
    assert result["step_id"] == "timing"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["door_sensor_inverted"] is True
    assert result["data"][CONF_DOOR_SENSOR] == "binary_sensor.door"


async def test_notify_service_without_entity_registry(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """iOS companion app notify targets exist only as services, not in entity registry."""
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")
    # Only register the service — no entity registry entry (iOS scenario)
    hass.services.async_register(
        "notify", "mobile_app_iphone", AsyncMock(return_value=None)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await _select_manual_trigger_mode(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_ENTITY: "binary_sensor.wm"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_iphone",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "timing"


async def test_config_flow_washdata_event_through_timing(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """WashData event mode skips entity selection and goes straight to presence."""
    hass.states.async_set("person.someone", "home")
    _register_notify_service(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "trigger_mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_MODE: TRIGGER_MODE_WASHDATA_EVENT},
    )
    assert result["step_id"] == "washdata_device"

    # No washdata entries exist — proceed with "All devices" (empty string).
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_WASHDATA_ENTRY_ID: ""},
    )
    assert result["step_id"] == "presence_notify_door"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
        },
    )
    assert result["step_id"] == "timing"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TRIGGER_MODE] == TRIGGER_MODE_WASHDATA_EVENT
    assert CONF_TRIGGER_ENTITY not in result["data"]
    assert result["data"][CONF_WASHDATA_ENTRY_ID] == ""
    mock_setup_entry.assert_called_once()


async def test_config_flow_washdata_event_with_device(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """WashData event mode with a discovered device pre-selects entry_id."""
    hass.states.async_set("person.someone", "home")
    _register_notify_service(hass)

    # Create a mock ha_washdata config entry so discovery finds it.
    washdata_entry = MockConfigEntry(
        domain="ha_washdata",
        title="Washing Machine",
        data={"name": "Washing Machine"},
    )
    washdata_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TRIGGER_MODE: TRIGGER_MODE_WASHDATA_EVENT},
    )
    assert result["step_id"] == "washdata_device"

    # Select the discovered device.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_WASHDATA_ENTRY_ID: washdata_entry.entry_id},
    )
    assert result["step_id"] == "presence_notify_door"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
        },
    )
    assert result["step_id"] == "timing"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TRIGGER_MODE] == TRIGGER_MODE_WASHDATA_EVENT
    assert result["data"][CONF_WASHDATA_ENTRY_ID] == washdata_entry.entry_id
    mock_setup_entry.assert_called_once()
