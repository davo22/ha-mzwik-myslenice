"""Sensors for the MZWiK Myślenice integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MzwikConfigEntry
from .const import DOMAIN
from .coordinator import MeterState, MzwikCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MzwikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for each configured meter."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for zamont_id in coordinator.data:
        entities.append(MzwikReadingSensor(coordinator, zamont_id))
        entities.append(MzwikConsumptionSensor(coordinator, zamont_id))
        entities.append(MzwikDailyAverageSensor(coordinator, zamont_id))
    async_add_entities(entities)


class _MzwikBase(CoordinatorEntity[MzwikCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MzwikCoordinator, zamont_id: str) -> None:
        super().__init__(coordinator)
        self._zamont_id = zamont_id
        state = coordinator.data[zamont_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, zamont_id)},
            manufacturer="MZWiK Myślenice",
            model=f"Wodomierz {state.serial}",
            name=f"Wodomierz {state.serial}",
        )

    @property
    def _state(self) -> MeterState:
        return self.coordinator.data[self._zamont_id]


class MzwikReadingSensor(_MzwikBase):
    """Current cumulative meter reading (wskazanie)."""

    _attr_translation_key = "reading"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: MzwikCoordinator, zamont_id: str) -> None:
        super().__init__(coordinator, zamont_id)
        self._attr_unique_id = f"{zamont_id}_reading"

    @property
    def native_value(self) -> float | None:
        return self._state.reading

    @property
    def extra_state_attributes(self) -> dict:
        d = self._state.reading_date
        return {"reading_date": d.isoformat() if d else None}


class MzwikConsumptionSensor(_MzwikBase):
    """Consumption booked in the last reading period (zuzycie)."""

    _attr_translation_key = "last_consumption"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MzwikCoordinator, zamont_id: str) -> None:
        super().__init__(coordinator, zamont_id)
        self._attr_unique_id = f"{zamont_id}_last_consumption"

    @property
    def native_value(self) -> float | None:
        return self._state.last_consumption


class MzwikDailyAverageSensor(_MzwikBase):
    """Portal-reported average daily consumption (sredniaDobowa)."""

    _attr_translation_key = "daily_average"
    _attr_native_unit_of_measurement = "m³/d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-outline"

    def __init__(self, coordinator: MzwikCoordinator, zamont_id: str) -> None:
        super().__init__(coordinator, zamont_id)
        self._attr_unique_id = f"{zamont_id}_daily_average"

    @property
    def native_value(self) -> float | None:
        return self._state.daily_average
