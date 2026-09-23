"""Config flow for the MZWiK Myślenice integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import MzwikApiClient, MzwikApiError, MzwikAuthError, MzwikMeter
from .const import (
    CONF_METERS,
    CONF_SEWAGE_METERS,
    CONF_SEWAGE_PRICE,
    CONF_WATER_PRICE,
    DEFAULT_SEWAGE_PRICE,
    DEFAULT_WATER_PRICE,
    DOMAIN,
)

CONF_METER_LABELS = "meter_labels"

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class MzwikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the MZWiK Myślenice config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MzwikOptionsFlow()

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
            labels = {
                m.zamont_id: (f"{m.serial} — {m.address}" if m.address else m.serial)
                for m in self._meters
            }
            return self.async_create_entry(
                title=f"MZWiK {self._username}",
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_METERS: user_input[CONF_METERS],
                    CONF_METER_LABELS: labels,
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


class MzwikOptionsFlow(OptionsFlow):
    """Set water/sewage unit prices and which meters include sewage."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        selected = self.config_entry.data.get(CONF_METERS, [])
        labels = self.config_entry.data.get(CONF_METER_LABELS, {})
        meter_options = [
            SelectOptionDict(value=mid, label=labels.get(mid, mid)) for mid in selected
        ]
        price = NumberSelector(
            NumberSelectorConfig(min=0, step=0.01, mode=NumberSelectorMode.BOX)
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WATER_PRICE,
                    default=opts.get(CONF_WATER_PRICE, DEFAULT_WATER_PRICE),
                ): price,
                vol.Required(
                    CONF_SEWAGE_PRICE,
                    default=opts.get(CONF_SEWAGE_PRICE, DEFAULT_SEWAGE_PRICE),
                ): price,
                vol.Optional(
                    CONF_SEWAGE_METERS,
                    default=opts.get(CONF_SEWAGE_METERS, selected),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=meter_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
