"""Tests for Wash Reminder config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.washreminder.config_flow import (
    _validate_trigger_state_for_sensor,
)
from custom_components.washreminder.const import (
    CONF_NOTIFY_TARGET,
    CONF_PERSON,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STATE,
    DOMAIN,
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


async def test_config_flow_user_timing_create_entry(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    hass.states.async_set("binary_sensor.wm", "off")
    hass.states.async_set("person.someone", "home")

    async def _dummy_notify(_call) -> None:
        return

    hass.services.async_register("notify", "mobile_app_phone", _dummy_notify)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_TRIGGER_ENTITY: "binary_sensor.wm",
            CONF_TRIGGER_STATE: "",
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
    mock_setup_entry.assert_called_once()


async def test_user_step_sensor_without_completion_state_errors(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("sensor.wm_state", "Idle")
    hass.states.async_set("person.someone", "home")

    async def _dummy_notify(_call) -> None:
        return

    hass.services.async_register("notify", "mobile_app_phone", _dummy_notify)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_TRIGGER_ENTITY: "sensor.wm_state",
            CONF_TRIGGER_STATE: "",
            CONF_PERSON: "person.someone",
            CONF_NOTIFY_TARGET: "notify.mobile_app_phone",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_TRIGGER_STATE: "trigger_state_required"}
