"""Tests for the (placeholder) Kerbl IoT config flow.

The real e-mail/password login step lands in a later build-out step; this
snapshot test locks down the placeholder's exact flow-result shape so a
regression is caught the moment the abort behaviour changes unexpectedly.
"""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from syrupy.assertion import SnapshotAssertion

from custom_components.kerbl_iot.const import DOMAIN


async def test_user_flow_aborts_as_not_yet_implemented(
    hass: HomeAssistant, snapshot: SnapshotAssertion
) -> None:
    """The user step currently aborts; this is replaced by real login later."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_implemented"
    assert result == snapshot
