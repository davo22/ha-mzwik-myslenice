"""Config flow for the MZWiK Myślenice integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import MzwikApiClient, MzwikApiError, MzwikAuthError, MzwikMeter
from .const import CONF_METERS, DOMAIN

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class MzwikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the MZWiK Myślenice config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._meters: list[MzwikMeter] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for client number and password, then verify by logging in."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_create_clientsession(self.hass)
            client = MzwikApiClient(session)
            try:
                await client.async_login(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                self._meters = await client.async_get_meters()
            except MzwikAuthError as err:
                _LOGGER.warning("MZWiK auth failed: %s", err)
                errors["base"] = "invalid_auth"
            except MzwikApiError as err:
                _LOGGER.warning("MZWiK connection failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                if not self._meters:
                    errors["base"] = "no_meters"
                else:
                    self._username = user_input[CONF_USERNAME]
                    self._password = user_input[CONF_PASSWORD]
                    return await self.async_step_meters()

        return self.async_show_form(
            step_id="user", data_schema=CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which meters to track."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"MZWiK {self._username}",
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_METERS: user_input[CONF_METERS],
                },
            )

        options = [
            SelectOptionDict(
                value=m.zamont_id,
                label=f"{m.serial} — {m.address}" if m.address else m.serial,
            )
            for m in self._meters
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_METERS, default=[m.zamont_id for m in self._meters]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="meters", data_schema=schema)
