"""Constants for the Kerbl IoT integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN = "kerbl_iot"

# Shared by every device Home Assistant creates for this integration: the
# SmartCoop root device and its five sub-component devices, registered by
# both the coordinator (coordinator.py, which pre-creates and links them)
# and the entity platforms (entity.py, whose entities declare matching
# device_info). Kept here, rather than in entity.py, because the
# coordinator also needs them and entity.py already imports from
# coordinator.py -- putting them in entity.py would make that a circular
# import.
MANUFACTURER = "Kerbl"
MODEL = "SmartCoop"

# Kerbl's SmartCoop is itself made up of distinct physical components -- a
# door, a light, a feeder, a water heater, a brightness sensor -- each
# modelled as its own Home Assistant device (own device page, own area
# assignment, own diagnostics download), linked back to the SmartCoop root
# device. These are the device-identifier suffixes and `translation_key`s
# for those five sub-devices.
SUB_DEVICE_DOOR = "door"
SUB_DEVICE_LIGHT = "light"
SUB_DEVICE_FEEDER = "feeder"
SUB_DEVICE_WATER_HEATER = "water_heater"
SUB_DEVICE_BRIGHTNESS = "brightness"
SUB_DEVICES = (
    SUB_DEVICE_DOOR,
    SUB_DEVICE_LIGHT,
    SUB_DEVICE_FEEDER,
    SUB_DEVICE_WATER_HEATER,
    SUB_DEVICE_BRIGHTNESS,
)

# Stored in a config entry's data alongside the standard CONF_ACCESS_TOKEN.
# Home Assistant has no built-in constant for an OAuth-style refresh token.
# This is a dict *key* name, not a credential value, hence the noqa below.
CONF_REFRESH_TOKEN: Final = "refresh_token"  # noqa: S105

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.COVER,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]
