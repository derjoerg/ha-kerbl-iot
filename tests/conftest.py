"""Shared fixtures for the Kerbl IoT integration test suite."""

from __future__ import annotations

from collections.abc import Generator

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Make custom_components/ discoverable by Home Assistant for every test.

    ``enable_custom_integrations`` is provided by
    pytest-homeassistant-custom-component; wrapping it as autouse means
    individual test modules don't need to request it explicitly.
    """
    yield
