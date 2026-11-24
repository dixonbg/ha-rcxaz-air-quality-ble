

# RCXAZ Air Quality Detector — Home Assistant Integration

[![Tests](https://github.com/dixonbg/ha-rcxaz-air-quality-ble/actions/workflows/tests.yml/badge.svg)](https://github.com/dixonbg/ha-rcxaz-air-quality-ble/actions/workflows/tests.yml)
[![Validate](https://github.com/dixonbg/ha-rcxaz-air-quality-ble/actions/workflows/validate.yml/badge.svg)](https://github.com/dixonbg/ha-rcxaz-air-quality-ble/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

A [HACS](https://hacs.xyz) custom integration that brings the **RCXAZ Air Quality Detector** into Home Assistant. It uses HA's native Bluetooth APIs, so both the built-in adapter **and** [ESPHome Bluetooth proxies](https://esphome.io/components/bluetooth_proxy.html) work out of the box.

This is a fork of [daweizhangau/ha-rcxaz-air-quality-ble](https://github.com/daweizhangau/ha-rcxaz-air-quality-ble).
Version 1.1 makes it installable through HACS, makes Bluetooth discovery work, and adds
[smoothing](#smoothing) so the once-a-second jitter no longer fills the recorder database.



<div style="display: flex; align-items: center; gap: 24px;">
   <div style="flex: 1;">
      <p>The device measures temperature, humidity, CO₂, TVOC, formaldehyde (HCHO), and particulate matter (PM1.0, PM2.5, PM10), pushing data via BLE notifications at ~1 Hz.</p>
   </div>
   <div>
      <img src="img/device_2co11.png" width="280" alt="RCXAZ Air Quality Detector">
   </div>
</div>

<div style="display: flex; align-items: center; gap: 24px;">
   <div style="flex: 1;">
      <p>Home Assistant integration showing sensor entities for the RCXAZ Air Quality Detector.</p>
   </div>
   <div>
      <img src="img/ha_screenshot.png" width="480" alt="RCXAZ Air Quality Detector">
   </div>
</div>

---

## Entities

| Entity | Type | Description |
|---|---|---|
| Temperature | Sensor | Current temperature in °C |
| Humidity | Sensor | Current relative humidity in % |
| CO₂ | Sensor | Carbon dioxide concentration in ppm |
| TVOC | Sensor | Total Volatile Organic Compounds in mg/m³ |
| HCHO | Sensor | Formaldehyde concentration in mg/m³ |
| PM1.0 | Sensor | Particulate matter <1.0 µm in µg/m³ |
| PM2.5 | Sensor | Particulate matter <2.5 µm in µg/m³ |
| PM10 | Sensor | Particulate matter <10 µm in µg/m³ |
| Connection Status | Sensor *(diagnostic)* | `Connected` / `Connecting` / `Disconnected` |
| RSSI | Sensor *(diagnostic, disabled by default)* | Signal strength in dBm, from the last advertisement. The device stops advertising while connected, so the value stays frozen. |
| Last Seen | Sensor *(diagnostic, disabled by default)* | Timestamp of the most recent reading |

The measurement sensors become unavailable when no reading has arrived for 2 minutes.

In a closed, unoccupied room CO₂ stays around 400–414 ppm and TVOC/HCHO at the bottom of their range.
The manufacturer does not say whether CO₂ comes from an NDIR sensor or is estimated, so treat it as indicative.

---

## Requirements

- Home Assistant 2024.11 or later (tested on 2026.11)
- A Bluetooth adapter accessible to HA (built-in, USB dongle, or [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/))
- RCXAZ Air Quality Detector (model 2CO11), powered on with Bluetooth enabled

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Add this repository URL and select category **Integration**.
3. Search for **RCXAZ Air Quality Detector** and click **Download**.
4. Restart Home Assistant.

### Manual

Copy the `custom_components/rcxaz_air_quality/` folder into your HA `config/custom_components/` directory and restart Home Assistant.

---

## Configuration

1. Power on the detector and enable Bluetooth.
2. Go to **Settings → Devices & Services** in Home Assistant.
3. A discovered **XS-**** notification will appear — click **Configure**.
   - If it does not appear, click **+ Add Integration** and search for *RCXAZ Air Quality*; it lists the detectors Home Assistant can currently hear. Close the RCXAZ phone app first: while the app is connected, the detector does not advertise.

The device pushes sensor data autonomously — no polling interval to configure.

### Smoothing

The detector sends a reading every second, and in a quiet room most of the movement is sensor jitter
(CO₂ hopping between 400 and 414 ppm, TVOC and HCHO in their last digit). Recorded as is, that is
roughly 160,000 state changes a day.

With smoothing on (the default), each measurement is averaged over time and a new value is recorded
only when the level really moves. A sudden real change, such as breathing on the sensor, is shown
right away: as soon as two consecutive readings leave the jitter band, the value jumps to them. A single
stray reading is ignored. Values are not offset or corrected.

On 73 hours of real data this cut 490,501 state changes to 3,349, with the recorded value staying within
about one unit of resolution of the 5-minute average.

Change it under **Settings → Devices & Services → RCXAZ Air Quality Detector → Configure**:

| Option | Default | |
|---|---|---|
| Smooth noisy readings | on | Off records every raw reading, as in 1.0. |
| Averaging time | 60 s | Longer is calmer and records less; slow changes show up later. |

`tools/backtest.py` replays a History CSV export (*History → ⋮ → Download data*) through the filter, to see
the effect of a different averaging time on your own data.

---

## Tested devices

| Model | Description | Year of Purchase |
|---|---|---|
| 2CO11 | 9-in-1, BLE | 2026 |

---

## Diagnostics

To help troubleshoot issues, open the device page and click **Download diagnostics**. The downloaded JSON contains connection state, last reading, signal strength, and other debug info — the MAC address is redacted automatically.

---

## **⚠️ Disclaimer**

> This is a personal hobby project. I am not affiliated with, endorsed by, or in any way connected to the manufacturer of this device. The BLE protocol was reverse-engineered from packet captures and may break with firmware updates. **Use at your own risk — no warranty of any kind is provided.**

---

For contributor and developer information see [DEVELOPMENT.md](DEVELOPMENT.md).
