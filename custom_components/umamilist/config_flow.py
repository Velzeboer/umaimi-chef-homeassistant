"""Set up UmamiList from the UI: server address, email and password (and the two-step code).

Only the session token the server hands out is stored, never the password. When the session
ends (logged out, or the account's password changed) Home Assistant asks for the password again.
With two-step login on, the code from the authenticator app comes along with the password; the
session doesn't ask for it again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UmamiListApi, UmamiListAuthError, UmamiListCodeError, UmamiListError
from .const import CONF_TOKEN, DOMAIN

CONF_CODE = "code"


class UmamiListConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _login(self, url: str, email: str, password: str, code: str | None) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Returns the login result, or None and the form errors."""
        api = UmamiListApi(async_get_clientsession(self.hass), url)
        try:
            return await api.login(email, password, code), {}
        except UmamiListAuthError:
            return None, {"base": "invalid_auth"}
        except UmamiListCodeError:
            return None, {"base": "invalid_code"}
        except UmamiListError:
            return None, {"base": "cannot_connect"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            result, errors = await self._login(url, user_input[CONF_EMAIL].strip(), user_input[CONF_PASSWORD], user_input.get(CONF_CODE))
            if result:
                await self.async_set_unique_id(result["user"]["id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Umaimi Chef ({result['user']['email']})",
                    data={CONF_URL: url, CONF_EMAIL: result["user"]["email"], CONF_TOKEN: result["token"]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({
                    vol.Required(CONF_URL): str,
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_CODE): str,
                }),
                # The code is only good for a few seconds: never filled in again.
                {k: v for k, v in (user_input or {}).items() if k != CONF_CODE} or None,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._login(entry.data[CONF_URL], entry.data[CONF_EMAIL], user_input[CONF_PASSWORD], user_input.get(CONF_CODE))
            if result:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: result["token"]})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str, vol.Optional(CONF_CODE): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
