"""Constants for the Kerbl IoT integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "kerbl_iot"

# Populated incrementally as entity platforms are implemented in later
# build-out steps (sensor, cover, light, button, binary_sensor, ...).
PLATFORMS: list[Platform] = []
