"""Config flow for the Kerbl IoT integration.

The first setup asks for e-mail and password, signs in once via
``KerblIOTApi.login()`` and then stores only the resulting access/refresh
tokens on the config entry -- the password itself is never persisted.

If the stored tokens can no longer be refreshed, ``async_setup_entry`` (see
``__init__.py``) raises ``ConfigEntryAuthFailed`` from the underlying
``KerblAuthenticationError``, which Home Assistant turns into a call to
:meth:`KerblIotConfigFlow.async_step_reauth`. That step asks for the
password again (the e-mail is kept, it identifies the existing entry) and
replaces the stored tokens with a fresh pair for the same account.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from kerbl_iot import (
    KerblAuthenticationError,
    KerblConnectionError,
    KerblIOTApi,
    KerblProtocolError,
)

from .const import CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


async def _async_sign_in(email: str, password: str) -> dict[str, str]:
    """Sign in once and return the token pair to persist on the entry.

    The client is given its own aiohttp session (never Home Assistant's
    shared one): the library only enables ``raise_for_status`` -- which its
    error handling and its automatic refresh-on-401 retry rely on -- for a
    session it creates and owns itself. Raises ``KerblAuthenticationError``,
    ``KerblConnectionError`` or ``KerblProtocolError`` on failure.
    """
    api = KerblIOTApi(email=email, password=password)
    try:
        await api.login()
        access_token, refresh_token = api.get_tokens()
    finally:
        await api.close()
    return {CONF_ACCESS_TOKEN: access_token, CONF_REFRESH_TOKEN: refresh_token}


class KerblIotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kerbl IoT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: e-mail/password login for a new account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            try:
                tokens = await _async_sign_in(email, user_input[CONF_PASSWORD])
            except KerblAuthenticationError:
                errors["base"] = "invalid_auth"
            except KerblConnectionError:
                errors["base"] = "cannot_connect"
            except KerblProtocolError:
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during Kerbl IoT login")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Kerbl IoT ({email})",
                    data={CONF_EMAIL: email, **tokens},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002 - required override signature
    ) -> ConfigFlowResult:
        """Handle reauthentication triggered by a ``KerblAuthenticationError``."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again and refresh the stored tokens."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            try:
                tokens = await _async_sign_in(email, user_input[CONF_PASSWORD])
            except KerblAuthenticationError:
                errors["base"] = "invalid_auth"
            except KerblConnectionError:
                errors["base"] = "cannot_connect"
            except KerblProtocolError:
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during Kerbl IoT reauthentication")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, **tokens},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={"email": email},
            errors=errors,
        )
