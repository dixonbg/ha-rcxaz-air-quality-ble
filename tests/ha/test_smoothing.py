"""Smoothing in the coordinator, availability and the options flow."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rcxaz_air_quality.const import (
    CONF_FILTER_ENABLED,
    CONF_FILTER_TAU,
    DOMAIN,
    STALE_AFTER,
)
from custom_components.rcxaz_air_quality.coordinator import RCXAZAirQualityCoordinator
from custom_components.rcxaz_air_quality.protocol import SensorReading
from custom_components.rcxaz_air_quality.sensor import (
    CO2Sensor,
    ConnectionStatusSensor,
    TemperatureSensor,
)
from tests.ha.conftest import TEST_ADDRESS, TEST_NAME, flow_ctx


def _entry(options=None):
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.unique_id = TEST_ADDRESS
    entry.title = TEST_NAME
    entry.options = options or {}
    return entry


async def _coordinator(hass, mock_ha_client, options):
    with patch(
        "custom_components.rcxaz_air_quality.coordinator.RCXAZAirQualityHAClient",
        return_value=mock_ha_client,
    ):
        coordinator = RCXAZAirQualityCoordinator(hass, _entry(options))
        await coordinator.async_setup()
    return coordinator


def _push(coordinator, client, page: SensorReading, t: float):
    client.last_page = page
    with patch("custom_components.rcxaz_air_quality.coordinator.time.monotonic", return_value=t):
        coordinator._on_reading(page)


AIR = lambda co2: SensorReading(co2_ppm=co2, tvoc_mgm3=0.007, hcho_mgm3=0.003, page_id=0x1004)
ENV = lambda t: SensorReading(temperature_c=t, humidity_pct=48, page_id=0x1004)


async def test_smoothing_on_by_default(hass, mock_ha_client, mock_bluetooth):
    coordinator = await _coordinator(hass, mock_ha_client, {})
    assert coordinator.filter_enabled and coordinator.filter_tau == 60
    for i, co2 in enumerate([400, 414] * 60):
        _push(coordinator, mock_ha_client, AIR(co2), float(i))
    assert 404 <= coordinator.value("co2") <= 410


async def test_smoothing_off_shows_raw(hass, mock_ha_client, mock_bluetooth):
    coordinator = await _coordinator(hass, mock_ha_client, {CONF_FILTER_ENABLED: False})
    _push(coordinator, mock_ha_client, AIR(400), 0.0)
    _push(coordinator, mock_ha_client, AIR(414), 1.0)
    assert coordinator.value("co2") == 414


async def test_only_fields_of_the_current_page_are_fed(hass, mock_ha_client, mock_bluetooth):
    coordinator = await _coordinator(hass, mock_ha_client, {})
    _push(coordinator, mock_ha_client, AIR(407), 0.0)
    before = coordinator._filters["co2"]._last_ts
    _push(coordinator, mock_ha_client, ENV(18.4), 1.0)   # env page carries no CO2
    assert coordinator._filters["co2"]._last_ts == before
    assert coordinator.value("temperature") == 18.4


async def test_custom_tau_from_options(hass, mock_ha_client, mock_bluetooth):
    coordinator = await _coordinator(hass, mock_ha_client, {CONF_FILTER_TAU: 120})
    assert coordinator._filters["co2"].tau == 120


def _sensor_with(last_seen, cls=CO2Sensor):
    coord = MagicMock(spec=RCXAZAirQualityCoordinator)
    coord.data = AIR(407)
    coord._client = MagicMock()
    coord._client.last_seen_at = last_seen
    coord.value.return_value = 407
    return cls(coord, _entry())


def test_measurement_unavailable_when_readings_stop():
    now = datetime.now(timezone.utc)
    assert _sensor_with(now).available
    assert not _sensor_with(now - timedelta(seconds=STALE_AFTER + 5)).available


def test_connection_status_stays_available():
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _sensor_with(old, ConnectionStatusSensor).available


def test_state_written_only_on_change():
    sensor = _sensor_with(datetime.now(timezone.utc), TemperatureSensor)
    sensor.coordinator.value.return_value = 18.4
    with patch.object(sensor, "async_write_ha_state") as write:
        sensor._handle_coordinator_update()
        sensor._handle_coordinator_update()
        assert write.call_count == 1
        sensor.coordinator.value.return_value = 18.5
        sensor._handle_coordinator_update()
        assert write.call_count == 2


async def test_options_flow(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=TEST_ADDRESS, data={"address": TEST_ADDRESS})
    entry.add_to_hass(hass)
    with flow_ctx(hass):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_FILTER_ENABLED: True, CONF_FILTER_TAU: 90.0},
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_FILTER_ENABLED: True, CONF_FILTER_TAU: 90}
