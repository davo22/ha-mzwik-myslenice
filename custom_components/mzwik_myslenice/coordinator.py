"""Coordinator for the MZWiK Myślenice integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MzwikApiClient, MzwikApiError, MzwikAuthError, MzwikReading
from .const import CONF_METERS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class MeterState:
    """Latest known state for one meter."""

    zamont_id: str
    serial: str
    address: str
    reading: float | None
    reading_date: date | None
    last_consumption: float | None
    daily_average: float | None


class MzwikCoordinator(DataUpdateCoordinator[dict[str, MeterState]]):
    """Logs in daily and reads the latest meter values."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        # A private cookie jar per account, not the shared HA session.
        self._session = async_create_clientsession(hass)
        self.client = MzwikApiClient(self._session)
        self._selected: list[str] = entry.data.get(CONF_METERS, [])

    async def _async_login(self) -> None:
        try:
            await self.client.async_login(
                self.entry.data[CONF_USERNAME], self.entry.data[CONF_PASSWORD]
            )
        except MzwikAuthError as err:
            raise UpdateFailed(f"Login rejected: {err}") from err
        except MzwikApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, MeterState]:
        await self._async_login()
        try:
            meters = await self.client.async_get_meters()
        except MzwikApiError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, MeterState] = {}
        for meter in meters:
            if self._selected and meter.zamont_id not in self._selected:
                continue
            try:
                readings = await self.client.async_get_readings(meter.zamont_id, limit=5)
            except MzwikApiError as err:
                raise UpdateFailed(str(err)) from err
            latest: MzwikReading | None = readings[0] if readings else None
            result[meter.zamont_id] = MeterState(
                zamont_id=meter.zamont_id,
                serial=meter.serial,
                address=meter.address,
                reading=latest.value if latest else meter.last_reading,
                reading_date=latest.reading_date if latest else meter.last_reading_date,
                last_consumption=latest.consumption if latest else None,
                daily_average=latest.daily_average if latest else None,
            )
        return result
