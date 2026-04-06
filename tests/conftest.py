"""Pytest configuration for Wash Reminder."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # noqa: ANN001
    """Enable custom_components in Home Assistant test fixtures."""
    yield
