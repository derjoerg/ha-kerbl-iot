"""Tests for KerblIotDataUpdateCoordinator.

Exercises the coordinator directly against a small in-memory double for
KerblIOTApi's transport (see ``tests/kerbl_fakes.py``) rather than through
the full config flow: no aiohttp or Socket.IO client is ever constructed,
so these tests never touch a real socket -- and stay portable to platforms
(see the project's own Windows/pytest-socket saga) where real socket
creation during test setup is a problem in itself.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kerbl_iot.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.kerbl_iot.coordinator import (
    FALLBACK_UPDATE_INTERVAL,
    KerblIotDataUpdateCoordinator,
)
from kerbl_iot import (
    KerblAuthenticationError,
    KerblConnectionError,
    KerblIOT,
    SmartCoop,
)
from tests.kerbl_fakes import SMART_COOP_ID, FakeApi, smart_coop_payload

ENTRY_DATA = {
    "email": "farmer@example.com",
    "access_token": "access-123",
    CONF_REFRESH_TOKEN: "refresh-456",
}


@pytest.fixture
async def make_coordinator(
    hass: HomeAssistant,
) -> AsyncGenerator[Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]]]:
    """Build a coordinator around a fake transport and shut it down afterward.

    ``async_config_entry_first_refresh`` requires the entry to be in
    ``SETUP_IN_PROGRESS``, which normally only happens partway through
    ``hass.config_entries.async_setup``; ``mock_state`` is
    pytest-homeassistant-custom-component's documented way to reach that
    state without driving the full config flow, matching how Home
    Assistant's own core tests exercise a coordinator in isolation.
    """
    created: list[KerblIotDataUpdateCoordinator] = []

    async def _factory(api: FakeApi) -> KerblIotDataUpdateCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
        coordinator = KerblIotDataUpdateCoordinator(hass, entry, KerblIOT(api))
        await coordinator.async_config_entry_first_refresh()
        created.append(coordinator)
        return coordinator

    yield _factory

    for coordinator in created:
        # Cancels the coordinator's own scheduled fallback-poll timer (and
        # any lingering KerblIOT log-refresh task) so it doesn't outlive the
        # test -- the same class of "lingering thread/timer" teardown
        # failure this project already hit once, in test_config_flow.py.
        await coordinator.async_shutdown()
        await coordinator.kerbl.async_close()


async def test_first_refresh_loads_devices_and_opens_push_channel(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """The first refresh loads all SmartCoops and connects the push channel."""
    api = FakeApi([smart_coop_payload()])
    coordinator = await make_coordinator(api)

    assert coordinator.last_update_success
    assert set(coordinator.data) == {SMART_COOP_ID}
    assert api.websocket_connected
    assert coordinator.is_smart_coop_available(SMART_COOP_ID)


def test_fallback_update_interval_is_15_to_20_minutes() -> None:
    """The polling fallback stays within the intended 15-20 minute range."""
    assert timedelta(minutes=15) <= FALLBACK_UPDATE_INTERVAL <= timedelta(minutes=20)


async def test_push_update_feeds_async_set_updated_data(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """A Socket.IO push update reaches listeners via async_set_updated_data."""
    api = FakeApi([smart_coop_payload()])
    coordinator = await make_coordinator(api)

    listener = MagicMock()
    coordinator.async_add_listener(listener)

    assert api.smart_coop_update_callback is not None
    pushed = SmartCoop.from_api(smart_coop_payload(light={"currentDimValue": 80}), api)
    await api.smart_coop_update_callback(pushed)

    assert coordinator.data[SMART_COOP_ID].light.current_dim_value == 80
    listener.assert_called_once()


async def test_websocket_connect_failure_is_not_fatal(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """A push-channel failure still leaves the coordinator on its polling fallback."""
    api = FakeApi([smart_coop_payload()])
    api.connect_error = KerblConnectionError("socket unreachable")
    coordinator = await make_coordinator(api)

    assert coordinator.last_update_success
    assert set(coordinator.data) == {SMART_COOP_ID}


async def test_load_failure_raises_auth_failed(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """An expired session during the first refresh triggers Home Assistant reauth."""
    api = FakeApi([smart_coop_payload()])
    api.load_error = KerblAuthenticationError("expired")

    with pytest.raises(ConfigEntryAuthFailed):
        await make_coordinator(api)


async def test_command_success_pushes_confirmed_state(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """A successful command presses the device and immediately pushes new state."""
    api = FakeApi([smart_coop_payload()])
    coordinator = await make_coordinator(api)

    listener = MagicMock()
    coordinator.async_add_listener(listener)

    await coordinator.async_trigger_feeder(SMART_COOP_ID)

    assert api.press_calls == ["feeder"]
    listener.assert_called_once()


async def test_command_translates_state_error(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """A command Kerbl refuses (bad device state) surfaces as HomeAssistantError."""
    api = FakeApi([smart_coop_payload(door={"state": 63})])  # DoorState.UNKNOWN
    coordinator = await make_coordinator(api)

    with pytest.raises(HomeAssistantError):
        await coordinator.async_open_door(SMART_COOP_ID)


async def test_command_unknown_smart_coop_raises(
    make_coordinator: Callable[[FakeApi], Awaitable[KerblIotDataUpdateCoordinator]],
) -> None:
    """Commanding a SmartCoop ID the coordinator doesn't know about is an error."""
    api = FakeApi([smart_coop_payload()])
    coordinator = await make_coordinator(api)

    with pytest.raises(HomeAssistantError):
        await coordinator.async_turn_on_light("does-not-exist")
