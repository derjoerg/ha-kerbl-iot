"""Config flow for the Kerbl IoT integration.

The interactive e-mail/password login step (which then stores only the
resulting access/refresh tokens, plus the reauth flow triggered by
``KerblAuthenticationError``) is implemented in a later build-out step.

This stub only registers the flow handler under ``DOMAIN`` so the
integration stays structurally valid -- ``manifest.json`` declares
``"config_flow": true`` -- and is importable and testable from the very
first commit.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class KerblIotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kerbl IoT."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, str] | None = None,  # noqa: ARG002 - kept for the real step signature
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Placeholder until e-mail/password login, token-only storage and
        multi-account support are implemented.
        """
        return self.async_abort(reason="not_implemented")
