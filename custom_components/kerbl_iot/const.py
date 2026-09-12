"""Constants for the Kerbl IoT integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN = "kerbl_iot"

# Shared by every device Home Assistant creates for this integration: the
# SmartCoop root device (entity.py) and its pre-registration counterpart in
# the coordinator (coordinator.py). Kept here, rather than in entity.py,
# because the coordinator also needs them and entity.py already imports
# from coordinator.py -- putting them in entity.py would make that a
# circular import.
MANUFACTURER = "Kerbl"
MODEL = "SmartCoop"

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
