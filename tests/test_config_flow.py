"""Tests for the Kerbl IoT config flow: e-mail/password login and reauth."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.kerbl_iot.const import CONF_REFRESH_TOKEN, DOMAIN
from kerbl_iot import KerblAuthenticationError, KerblConnectionError

TEST_EMAIL = "farmer@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"
TEST_TOKENS = {"access_token": "access-123", CONF_REFRESH_TOKEN: "refresh-456"}


@pytest.fixture
def mock_sign_in() -> Generator[AsyncMock]:
    """Replace the flow's login helper so no real network call happens."""
    with patch(
        "custom_components.kerbl_iot.config_flow._async_sign_in",
        AsyncMock(return_value=TEST_TOKENS),
    ) as mock:
        yield mock


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_sign_in: AsyncMock, snapshot: SnapshotAssertion
) -> None:
    """A successful e-mail/password login creates one entry with tokens only."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Kerbl IoT ({TEST_EMAIL})"
    assert result["data"] == {"email": TEST_EMAIL, **TEST_TOKENS}
    mock_sign_in.assert_awaited_once_with(TEST_EMAIL, TEST_PASSWORD)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == TEST_EMAIL.lower()
    assert entry.data == snapshot


async def test_user_flow_duplicate_account_aborts(
    hass: HomeAssistant, mock_sign_in: AsyncMock
) -> None:
    """A second account with the same (case-insensitive) e-mail is rejected."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.lower(),
        data={"email": TEST_EMAIL, **TEST_TOKENS},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": TEST_EMAIL.upper(), "password": TEST_PASSWORD},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_sign_in.assert_not_awaited()


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (KerblAuthenticationError("bad credentials"), "invalid_auth"),
        (KerblConnectionError("unreachable"), "cannot_connect"),
    ],
)
async def test_user_flow_shows_error(
    hass: HomeAssistant,
    mock_sign_in: AsyncMock,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Login failures re-show the form with a translatable error code."""
    mock_sign_in.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": TEST_EMAIL, "password": "wrong"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected_error}


async def test_reauth_flow_updates_tokens(
    hass: HomeAssistant, mock_sign_in: AsyncMock
) -> None:
    """A successful reauth replaces the stored tokens and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.lower(),
        data={
            "email": TEST_EMAIL,
            "access_token": "stale",
            CONF_REFRESH_TOKEN: "stale",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {"email": TEST_EMAIL}

    # Reauth success reloads the entry, which re-enters async_setup_entry;
    # stub out its I/O so the test stays offline.
    with (
        patch("kerbl_iot.KerblIOT.load", AsyncMock(return_value=None)),
        patch("kerbl_iot.KerblIOT.async_close", AsyncMock(return_value=None)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": TEST_PASSWORD}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {"email": TEST_EMAIL, **TEST_TOKENS}
    mock_sign_in.assert_awaited_once_with(TEST_EMAIL, TEST_PASSWORD)


async def test_reauth_flow_invalid_password_keeps_form(
    hass: HomeAssistant, mock_sign_in: AsyncMock
) -> None:
    """A wrong password during reauth re-shows the form instead of aborting."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.lower(),
        data={
            "email": TEST_EMAIL,
            "access_token": "stale",
            CONF_REFRESH_TOKEN: "stale",
        },
    )
    entry.add_to_hass(hass)
    mock_sign_in.side_effect = KerblAuthenticationError("bad credentials")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "still-wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["access_token"] == "stale"
