"""Tests for the Kerbl IoT entity platforms (light, cover, button, sensor,
binary_sensor).

Drives a full config entry setup (so all five platforms are actually
forwarded and wired up) against the same in-memory `FakeApi` transport used
by test_coordinator.py -- injected by patching the `KerblIOTApi` name inside
`custom_components.kerbl_iot`, since `async_setup_entry` constructs it
itself. Entities are looked up by unique_id via the entity registry rather
than by guessing translated entity_ids, so these tests don't depend on
whether Home Assistant's translation cache happens to be loaded.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kerbl_iot.const import CONF_REFRESH_TOKEN, DOMAIN
from kerbl_iot import SmartCoopLog
from tests.kerbl_fakes import SMART_COOP_ID, FakeApi, smart_coop_payload

ENTRY_DATA = {
    "email": "farmer@example.com",
    "access_token": "access-123",
    CONF_REFRESH_TOKEN: "refresh-456",
}


def _unique_id(key: str) -> str:
    return f"{SMART_COOP_ID}_{key}"


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Look up an entity_id by unique_id, independent of translated names."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, _unique_id(key))
    assert entity_id is not None, f"No {platform} entity registered for key {key!r}"
    return entity_id


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[FakeApi, MockConfigEntry]]:
    """Set up one config entry against a fresh FakeApi and unload it after.

    ``FakeApi`` doesn't accept the real KerblIOTApi constructor's
    (email, password, session) arguments, so the class itself -- not an
    instance -- is patched: ``async_setup_entry`` calls it once with those
    arguments and gets this fixture's ``api`` back regardless, since the
    patched callable's ``return_value`` ignores whatever it's called with.
    """
    api = FakeApi([smart_coop_payload()])

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kerbl_iot.KerblIOTApi",
        MagicMock(return_value=api),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        yield api, entry

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_expected_entities_are_created(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Every documented entity exists, keyed by its stable unique_id."""
    del setup_entry  # only needed to drive the config entry setup
    expected_keys_by_platform = {
        "light": ["light"],
        "cover": ["door"],
        "button": ["feed_now", "acknowledge_errors"],
        "sensor": [
            "air_temperature",
            "water_temperature",
            "brightness",
            "firmware_version",
            "door_closes_in",
            "door_state",
            "current_error",
        ],
        "binary_sensor": [
            "online",
            "feeding_in_progress",
            "feed_empty",
            "feeding_locked",
            "water_sensor",
            "external_brightness_sensor",
        ],
    }
    registry = er.async_get(hass)
    for platform, keys in expected_keys_by_platform.items():
        for key in keys:
            entity_id = registry.async_get_entity_id(platform, DOMAIN, _unique_id(key))
            assert entity_id is not None, f"missing {platform} entity for {key!r}"


async def test_door_entities_are_skipped_without_a_door(hass: HomeAssistant) -> None:
    """A SmartCoop reporting has_no_door=True gets no cover or door sensors."""
    api = FakeApi([smart_coop_payload(door={"state": 79, "hasNoDoor": True})])
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
    )
    entry.add_to_hass(hass)

    with patch("custom_components.kerbl_iot.KerblIOTApi", MagicMock(return_value=api)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        assert registry.async_get_entity_id("cover", DOMAIN, _unique_id("door")) is None
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, _unique_id("door_state"))
            is None
        )
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, _unique_id("door_closes_in"))
            is None
        )
        # Non-door entities are unaffected.
        light_entity_id = registry.async_get_entity_id(
            "light", DOMAIN, _unique_id("light")
        )
        assert light_entity_id is not None

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_light_turn_on_reaches_the_device(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Calling light.turn_on presses the light and reports it on."""
    api, _entry = setup_entry
    entity_id = _entity_id(hass, "light", "light")
    assert hass.states.get(entity_id).state == "off"

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert "light" in api.press_calls
    assert hass.states.get(entity_id).state == "on"


async def test_cover_close_reaches_the_device(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Calling cover.close_cover presses the door and reports it closed."""
    api, _entry = setup_entry
    entity_id = _entity_id(hass, "cover", "door")
    assert hass.states.get(entity_id).state == "open"

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert "door" in api.press_calls
    assert hass.states.get(entity_id).state == "closed"


async def test_feed_button_reaches_the_device(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Pressing the feed-now button triggers a manual feeding."""
    api, _entry = setup_entry
    entity_id = _entity_id(hass, "button", "feed_now")

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert api.press_calls == ["feeder"]


async def test_acknowledge_errors_button_without_active_errors_fails(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Pressing acknowledge-errors with nothing active raises, not silently no-ops."""
    _api, _entry = setup_entry
    entity_id = _entity_id(hass, "button", "acknowledge_errors")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )


async def test_acknowledge_errors_button_with_active_errors_succeeds(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """An active log entry's error code is acknowledged on press."""
    api, entry = setup_entry
    api.logs[SMART_COOP_ID] = [
        SmartCoopLog(
            time="12:00",
            date="2024.01.01",
            active=True,
            error_code=42,
            error_key="err.some_error",
            level="error",
            occurred_at=None,
            received_at=datetime.now(UTC),
        )
    ]
    # KerblIOT caches logs from its own load(); setting api.logs above
    # doesn't retroactively update that cache, so refresh it explicitly --
    # the same way a real error occurring would (see _schedule_log_refresh).
    await entry.runtime_data.kerbl.refresh_smart_coop_logs(SMART_COOP_ID)
    entity_id = _entity_id(hass, "button", "acknowledge_errors")

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert api.press_calls == ["acknowledge"]


async def test_sensor_values_reflect_the_smart_coop(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Sensor entities report the values from the loaded SmartCoop."""
    hass_states = {
        "air_temperature": "18.5",
        "water_temperature": "12.5",
        "brightness": "500",
        "firmware_version": "1.2.3",
        "door_state": "open",
        # current_error_reason is unset in the test payload -> None -> "unknown"
        "current_error": "unknown",
    }
    for key, expected in hass_states.items():
        entity_id = _entity_id(hass, "sensor", key)
        assert hass.states.get(entity_id).state == expected, key


async def test_binary_sensor_values_reflect_the_smart_coop(
    hass: HomeAssistant, setup_entry: tuple[FakeApi, MockConfigEntry]
) -> None:
    """Binary sensor entities report on/off correctly, including the inverted one."""
    expected = {
        "online": "on",
        "feeding_in_progress": "off",
        "feed_empty": "off",  # is_feed_full=True in the default payload
        "feeding_locked": "unknown",  # not set in the default payload -> None
        "water_sensor": "on",
        "external_brightness_sensor": "on",
    }
    for key, state in expected.items():
        entity_id = _entity_id(hass, "binary_sensor", key)
        assert hass.states.get(entity_id).state == state, key


async def test_offline_smart_coop_entities_are_unavailable(hass: HomeAssistant) -> None:
    """A SmartCoop reported offline makes its entities unavailable, not just 'off'."""
    api = FakeApi([smart_coop_payload(isOnline=False)])
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="farmer@example.com", data=ENTRY_DATA
    )
    entry.add_to_hass(hass)

    with patch("custom_components.kerbl_iot.KerblIOTApi", MagicMock(return_value=api)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = _entity_id(hass, "light", "light")
        assert hass.states.get(entity_id).state == "unavailable"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
