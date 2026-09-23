"""Backfill averaged daily water consumption into long-term statistics.

The utility reads the meters by hand every few months, so all we get is a
consumption figure (`zuzycie`) per reading period. We spread each period's
consumption evenly across its days — e.g. 30 m³ over 10 days becomes 3 m³/day —
and import that as one point per day with a running cumulative sum. The result
is a stepped daily series that is flat within a period and steps up at each new
reading, which is an honest picture of what a manually-read meter actually knows.

Consumption (not the dial value `wskazanie`) is used to build the sum, so a
physical meter swap — which resets the dial — does not corrupt the history.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import MzwikApiClient, MzwikApiError, MzwikMeter
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def statistic_id(meter: MzwikMeter) -> str:
    """External statistic id for one meter's consumption history."""
    return f"{DOMAIN}:water_{_slug(meter.serial)}"


def cost_statistic_id(meter: MzwikMeter) -> str:
    """External statistic id for one meter's cost history."""
    return f"{DOMAIN}:cost_{_slug(meter.serial)}"


def _slug(serial: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in serial.lower())


async def async_has_history(hass: HomeAssistant, sid: str) -> bool:
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, sid, True, {"sum"}
    )
    return bool(last.get(sid))


def _daily_consumption(readings: list) -> dict[datetime, float]:
    """Spread each reading period's consumption evenly across its days."""
    readings = [r for r in readings if r.reading_date is not None]
    readings.sort(key=lambda r: r.reading_date)
    daily: dict[datetime, float] = {}
    for prev, cur in zip(readings, readings[1:]):
        span = (cur.reading_date - prev.reading_date).days
        if span <= 0:
            continue
        per_day = cur.consumption / span
        for offset in range(span):
            day = prev.reading_date + timedelta(days=offset + 1)
            start = dt_util.as_utc(
                datetime(day.year, day.month, day.day, tzinfo=dt_util.DEFAULT_TIME_ZONE)
            )
            daily[start] = per_day
    return daily


def _cumulative(daily: dict[datetime, float], factor: float = 1.0) -> list[StatisticData]:
    running = 0.0
    points: list[StatisticData] = []
    for start in sorted(daily):
        value = daily[start] * factor
        running += value
        points.append(StatisticData(start=start, state=value, sum=running))
    return points


async def async_import_meter_history(
    hass: HomeAssistant,
    client: MzwikApiClient,
    meter: MzwikMeter,
    *,
    unit_price: float | None = None,
) -> int:
    """Import averaged daily consumption (and cost, if a price is given).

    Returns the number of daily points written for the consumption statistic.
    `unit_price` is PLN per m³ already summed for this meter (water, plus sewage
    when it applies); when None or 0, no cost statistic is written.
    """
    try:
        readings = await client.async_get_readings(meter.zamont_id, limit=500)
    except MzwikApiError as err:
        _LOGGER.warning("Cannot fetch readings for meter %s: %s", meter.serial, err)
        return 0

    daily = _daily_consumption(readings)
    if not daily:
        _LOGGER.info("Meter %s has too few readings to build history", meter.serial)
        return 0

    points = _cumulative(daily)
    async_add_external_statistics(
        hass,
        StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Woda {meter.serial}",
            source=DOMAIN,
            statistic_id=statistic_id(meter),
            unit_of_measurement="m³",
        ),
        points,
    )

    if unit_price:
        cost_points = _cumulative(daily, factor=unit_price)
        async_add_external_statistics(
            hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"Woda {meter.serial} — koszt",
                source=DOMAIN,
                statistic_id=cost_statistic_id(meter),
                unit_of_measurement="PLN",
            ),
            cost_points,
        )

    _LOGGER.info(
        "Imported %s daily points (%.2f m³%s) for meter %s",
        len(points),
        sum(daily.values()),
        f", {sum(daily.values()) * unit_price:.2f} PLN" if unit_price else "",
        meter.serial,
    )
    return len(points)
