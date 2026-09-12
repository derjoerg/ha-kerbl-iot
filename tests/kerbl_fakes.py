"""Shared fake KerblIOTApi transport for coordinator/entity tests.

Bypasses aiohttp and Socket.IO entirely -- see test_coordinator.py's module
docstring for why that matters on this project (a real Windows/pytest-socket
incompatibility hit earlier in this project's CI work).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from kerbl_iot import CommandResult, SmartCoop, SmartCoopLog

SMART_COOP_ID = "coop-1"


def smart_coop_payload(**overrides: Any) -> dict[str, Any]:
    """Build one SmartCoop API payload, with sane defaults for tests."""
    payload: dict[str, Any] = {
        "id": SMART_COOP_ID,
        "userId": "user-1",
        "description": "Henhouse",
        "isOnline": True,
        "light": {"currentDimValue": 0},
        "door": {"state": 79},  # DoorState.OPEN
        "feeder": {"isFeedFull": True, "feedingInProgress": False},
        "waterHeater": {"waterTemperature": 12.5, "waterSensorState": True},
        "brightness": {"currentBrightness": 500, "externalSensorConnected": True},
        "airTemperature": 18.5,
        "firmwareVersion": "1.2.3",
    }
    payload.update(overrides)
    return payload


class FakeApi:
    """Minimal double for the KerblIOTApi surface KerblIOT relies on.

    Command methods (``_press_light`` etc.) mutate the underlying payload
    and, when a consumer has registered for push updates, immediately feed
    the new state back through ``smart_coop_update_callback`` -- the same
    path a real Socket.IO confirmation would take. Kerbl's own commands are
    plain manual toggles, so that's also what these do: press = flip.
    Without this, KerblIOT's own confirm-and-wait logic (see
    ``SmartCoopDoor._set_state`` / ``SmartCoopLight._set_state``) would wait
    on an event nothing ever sets, hanging until its real 30s timeout.
    """

    def __init__(self, smart_coop_payloads: list[dict[str, Any]]) -> None:
        self.payloads = smart_coop_payloads
        self.websocket_connected = False
        self.press_calls: list[str] = []
        self.load_error: Exception | None = None
        self.connect_error: Exception | None = None
        self.logs: dict[str, list[SmartCoopLog]] = {}
        self.smart_coop_update_callback: (
            Callable[[SmartCoop], Awaitable[None]] | None
        ) = None

    def payload(self, smart_coop_id: str) -> dict[str, Any]:
        """Return the mutable payload dict for one SmartCoop ID."""
        return next(p for p in self.payloads if p["id"] == smart_coop_id)

    def restore_tokens(self, access_token: str, refresh_token: str) -> None:
        """No-op: this fake never checks tokens, only KerblIOTApi does."""

    async def confirm(self, smart_coop_id: str, **overrides: Any) -> None:
        """Simulate the device pushing a confirmed state after a command."""
        payload = self.payload(smart_coop_id)
        payload.update(overrides)
        if self.smart_coop_update_callback is not None:
            await self.smart_coop_update_callback(SmartCoop.from_api(payload, self))

    async def get_smart_coops(self) -> list[SmartCoop]:
        """Return freshly parsed SmartCoops, as a real GET would."""
        if self.load_error is not None:
            raise self.load_error
        return [SmartCoop.from_api(payload, self) for payload in self.payloads]

    async def get_smart_coop_logs(self, smart_coop_id: str) -> list[SmartCoopLog]:
        """Return the configured logs for one SmartCoop."""
        return self.logs.get(smart_coop_id, [])

    async def connect_websocket(
        self,
        smart_coops: list[SmartCoop],
        debug: bool = False,
        *,
        reconnection_attempts: int = 0,
        reconnection_delay: float = 1.0,
    ) -> None:
        """Simulate a Socket.IO connect, or raise a configured failure."""
        if self.connect_error is not None:
            raise self.connect_error
        self.websocket_connected = bool(smart_coops)

    async def close(self) -> None:
        """Simulate closing the transport."""
        self.websocket_connected = False

    def register_smart_coop_update_callback(
        self, callback: Callable[[SmartCoop], Awaitable[None]]
    ) -> None:
        """Capture the callback so tests (and `confirm`) can push updates."""
        self.smart_coop_update_callback = callback

    def register_socket_connect_callback(
        self, callback: Callable[[], Awaitable[None]]
    ) -> None:
        """Ignore: reconnect behavior isn't exercised by these tests."""

    def register_socket_disconnect_callback(
        self, callback: Callable[[], Awaitable[None]]
    ) -> None:
        """Ignore: disconnect behavior isn't exercised by these tests."""

    async def _press_light(self, smart_coop_id: str) -> CommandResult:
        self.press_calls.append("light")
        light = self.payload(smart_coop_id).get("light", {})
        current = light.get("currentDimValue") or 0
        new_value = 0 if current else 100
        await self.confirm(smart_coop_id, light={"currentDimValue": new_value})
        return CommandResult(success=True, command_count=1)

    async def _press_feeder(self, smart_coop_id: str) -> CommandResult:
        self.press_calls.append("feeder")
        return CommandResult(success=True, command_count=1)

    async def _press_door(self, smart_coop_id: str) -> CommandResult:
        self.press_calls.append("door")
        current_state = self.payload(smart_coop_id).get("door", {}).get("state")
        new_state = 67 if current_state == 79 else 79  # DoorState.CLOSED <-> OPEN
        await self.confirm(smart_coop_id, door={"state": new_state})
        return CommandResult(success=True, command_count=1)

    async def _acknowledge_errors(
        self, smart_coop_id: str, error_codes: list[int]
    ) -> CommandResult:
        self.press_calls.append("acknowledge")
        return CommandResult(success=True, command_count=len(error_codes))
