"""The MZWiK Myślenice (eBOK) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_IMPORT_VERSION,
    CONF_METERS,
    CONF_SEWAGE_METERS,
    CONF_SEWAGE_PRICE,
    CONF_WATER_PRICE,
    DEFAULT_SEWAGE_PRICE,
    DEFAULT_WATER_PRICE,
    DOMAIN,
    IMPORT_VERSION,
    SERVICE_IMPORT_HISTORY,
)
from .coordinator import MzwikCoordinator
from .statistics import async_has_history, async_import_meter_history, statistic_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

MzwikConfigEntry = ConfigEntry[MzwikCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MzwikConfigEntry) -> bool:
    """Set up MZWiK Myślenice from a config entry."""
    coordinator = MzwikCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    # Re-import (rebuilds cost statistics too) whenever prices/options change.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    outdated = entry.data.get(CONF_IMPORT_VERSION) != IMPORT_VERSION
    needs_import = outdated
    if not needs_import:
        for meter in await coordinator.client.async_get_meters():
            if coordinator.data and meter.zamont_id not in coordinator.data:
                continue
            if not await async_has_history(hass, statistic_id(meter)):
                needs_import = True
                break

    if needs_import:
        entry.async_create_background_task(
            hass, _async_import(hass, entry), name="mzwik history import"
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MzwikConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _unit_price(entry: MzwikConfigEntry, zamont_id: str) -> float:
    """PLN per m³ for one meter: water always, sewage only where it applies."""
    opts = entry.options
    water = float(opts.get(CONF_WATER_PRICE, DEFAULT_WATER_PRICE))
    sewage = float(opts.get(CONF_SEWAGE_PRICE, DEFAULT_SEWAGE_PRICE))
    # Default (no options set yet): charge sewage on every meter. Once the user
    # configures sewage_meters, only the listed meters get sewage.
    sewage_meters = opts.get(CONF_SEWAGE_METERS)
    applies = sewage_meters is None or zamont_id in sewage_meters
    return water + (sewage if applies else 0.0)


async def _async_options_updated(hass: HomeAssistant, entry: MzwikConfigEntry) -> None:
    """Rebuild statistics when prices/options change."""
    await _async_import(hass, entry)


async def _async_import(hass: HomeAssistant, entry: MzwikConfigEntry) -> None:
    """Import averaged history (m³ and cost) for every configured meter."""
    coordinator = entry.runtime_data
    selected = entry.data.get(CONF_METERS, [])
    try:
        meters = await coordinator.client.async_get_meters()
    except Exception:  # noqa: BLE001 - background task must not die silently
        _LOGGER.exception("History import: cannot list meters")
        return

    total = 0
    for meter in meters:
        if selected and meter.zamont_id not in selected:
            continue
        try:
            total += await async_import_meter_history(
                hass,
                coordinator.client,
                meter,
                unit_price=_unit_price(entry, meter.zamont_id),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("History import failed for meter %s", meter.serial)

    if total:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_IMPORT_VERSION: IMPORT_VERSION}
        )


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_IMPORT_HISTORY):
        return

    async def _handle_import(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await _async_import(hass, entry)

    hass.services.async_register(DOMAIN, SERVICE_IMPORT_HISTORY, _handle_import)
