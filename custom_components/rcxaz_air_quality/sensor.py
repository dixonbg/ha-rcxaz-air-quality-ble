"""Sensor entities for the RCXAZ Air Quality Detector."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:  # HA 2026.x: unit enums replace the CONCENTRATION_* constants (removed in 2027.8)
    from homeassistant.const import UnitOfDensity, UnitOfRatio

    UNIT_UG_M3 = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    UNIT_MG_M3 = UnitOfDensity.MILLIGRAMS_PER_CUBIC_METER
    UNIT_PPM = UnitOfRatio.PARTS_PER_MILLION
except ImportError:  # older Home Assistant
    from homeassistant.const import (
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER as UNIT_UG_M3,
        CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER as UNIT_MG_M3,
        CONCENTRATION_PARTS_PER_MILLION as UNIT_PPM,
    )

from .const import (
    CONN_STATUS_CONNECTED,
    CONN_STATUS_CONNECTING,
    CONN_STATUS_DISCONNECTED,
    DOMAIN,
    STALE_AFTER,
    SUFFIX_CO2,
    SUFFIX_CONNECTION_STATUS,
    SUFFIX_HCHO,
    SUFFIX_HUMIDITY,
    SUFFIX_LAST_SEEN,
    SUFFIX_PM10,
    SUFFIX_PM1_0,
    SUFFIX_PM2_5,
    SUFFIX_RSSI,
    SUFFIX_TEMPERATURE,
    SUFFIX_TVOC,
)
from .coordinator import RCXAZAirQualityCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RCXAZ Air Quality sensor entities."""
    coordinator: RCXAZAirQualityCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TemperatureSensor(coordinator, entry),
        HumiditySensor(coordinator, entry),
        CO2Sensor(coordinator, entry),
        TVOCSensor(coordinator, entry),
        HCHOSensor(coordinator, entry),
        PM1_0Sensor(coordinator, entry),
        PM2_5Sensor(coordinator, entry),
        PM10Sensor(coordinator, entry),
        ConnectionStatusSensor(coordinator, entry),
        RSSISensor(coordinator, entry),
        LastSeenSensor(coordinator, entry),
    ])


# ── Base classes ───────────────────────────────────────────────────────────────

class RCXAZAirQualitySensor(CoordinatorEntity[RCXAZAirQualityCoordinator], SensorEntity):
    """Base sensor for the RCXAZ Air Quality Detector.

    The device pushes a page about once a second. The state is written only
    when this entity's value or availability actually changed, so unchanged
    entities do not put an event on the bus for every page.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RCXAZAirQualityCoordinator,
        entry: ConfigEntry,
        suffix: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_{suffix}"
        self._attr_translation_key = suffix
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, entry.unique_id)},
            manufacturer="Nobito (Shenzhen) Technology Co., LTD",
            model="2CO11",
            name=entry.title,
        )
        self._written: tuple | None = None

    @property
    def available(self) -> bool:
        """Available while readings keep arriving."""
        if self.coordinator.data is None:
            return False
        client = self.coordinator._client
        last_seen = client.last_seen_at if client is not None else None
        if not isinstance(last_seen, datetime):
            return True  # no timing information: trust the data we have
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
        return age < STALE_AFTER

    @callback
    def _handle_coordinator_update(self) -> None:
        snapshot = (self.available, self.native_value)
        if snapshot == self._written:
            return
        self._written = snapshot
        self.async_write_ha_state()


class _MeasurementSensor(RCXAZAirQualitySensor):
    """A measured value, smoothed by the coordinator's noise filter."""

    _key: str
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RCXAZAirQualityCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, self._key)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.value(self._key)


# ── Measurements ───────────────────────────────────────────────────────────────

class TemperatureSensor(_MeasurementSensor):
    """Temperature sensor."""

    _key = SUFFIX_TEMPERATURE
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1


class HumiditySensor(_MeasurementSensor):
    """Relative humidity sensor."""

    _key = SUFFIX_HUMIDITY
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE


class CO2Sensor(_MeasurementSensor):
    """CO₂ sensor."""

    _key = SUFFIX_CO2
    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = UNIT_PPM


class TVOCSensor(_MeasurementSensor):
    """Total volatile organic compounds sensor."""

    _key = SUFFIX_TVOC
    _attr_device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS
    _attr_native_unit_of_measurement = UNIT_MG_M3
    _attr_suggested_display_precision = 3


class HCHOSensor(_MeasurementSensor):
    """Formaldehyde sensor (Home Assistant has no device class for it)."""

    _key = SUFFIX_HCHO
    _attr_native_unit_of_measurement = UNIT_MG_M3
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:molecule"


class PM1_0Sensor(_MeasurementSensor):
    """PM1.0 particulate sensor."""

    _key = SUFFIX_PM1_0
    _attr_device_class = SensorDeviceClass.PM1
    _attr_native_unit_of_measurement = UNIT_UG_M3


class PM2_5Sensor(_MeasurementSensor):
    """PM2.5 particulate sensor."""

    _key = SUFFIX_PM2_5
    _attr_device_class = SensorDeviceClass.PM25
    _attr_native_unit_of_measurement = UNIT_UG_M3


class PM10Sensor(_MeasurementSensor):
    """PM10 particulate sensor."""

    _key = SUFFIX_PM10
    _attr_device_class = SensorDeviceClass.PM10
    _attr_native_unit_of_measurement = UNIT_UG_M3


# ── Diagnostic sensors ─────────────────────────────────────────────────────────

class ConnectionStatusSensor(RCXAZAirQualitySensor):
    """BLE connection state: Connected / Connecting / Disconnected."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        CONN_STATUS_CONNECTED,
        CONN_STATUS_CONNECTING,
        CONN_STATUS_DISCONNECTED,
    ]
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: RCXAZAirQualityCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SUFFIX_CONNECTION_STATUS)

    @property
    def available(self) -> bool:
        """Always available — reporting a lost connection is its job."""
        return True

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return CONN_STATUS_DISCONNECTED
        if self.coordinator._client is None:
            return CONN_STATUS_DISCONNECTED
        return self.coordinator.client.connection_status


class RSSISensor(RCXAZAirQualitySensor):
    """Bluetooth signal strength in dBm.

    Disabled by default: it comes from the last advertisement, and the device
    stops advertising while it is connected, so the value stays frozen.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:bluetooth"

    def __init__(self, coordinator: RCXAZAirQualityCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SUFFIX_RSSI)

    @property
    def native_value(self) -> int | None:
        return self.coordinator.get_rssi()


class LastSeenSensor(RCXAZAirQualitySensor):
    """UTC timestamp of the most recent successful reading.

    Disabled by default to avoid flooding the activity log with
    per-second timestamp updates.  Enable manually if needed.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: RCXAZAirQualityCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, SUFFIX_LAST_SEEN)

    @property
    def available(self) -> bool:
        return self.coordinator._client is not None

    @property
    def native_value(self) -> datetime | None:
        if self.coordinator._client is None:
            return None
        return self.coordinator.client.last_seen_at
