# 💧 dbus-ads1115: Venus OS Tank Integration

[![Platform: Venus OS](https://img.shields.io/badge/Platform-Venus%20OS-orange.svg)](https://www.victronenergy.com/panel-systems-remote-monitoring/venus-os)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Hardware: ADS1115](https://img.shields.io/badge/Hardware-ADS1115%20ADC-blue.svg)](https://www.ti.com/product/ADS1115)

Connect resistive level sensors (water, fuel, oil) to your **Victron Energy Venus OS** system using a high-precision 16-bit ADS1115 ADC. A cost-effective, accurate, and natively integrated solution for DIY marine and off-grid power systems.

---

## 🚀 Features

- **Native Integration:** Tanks appear as official devices in the Remote Console and VRM Portal.
- **GUI-Based Calibration:** Set empty/full resistance values (Ω) directly from the touchscreen or Remote Console — no SSH or file editing required.
- **Wiring Presets:** One-tap selection for European (0–180 Ω) and US/NMEA (240–30 Ω) standards.
- **Custom Tank Shapes:** Piecewise correction curves for non-linear tanks (cylindrical, D-shaped, conical) with up to 10 points.
- **Multi-channel Support:** Up to 4 sensors on a single ADS1115 (channels A0–A3).
- **Stable I2C Access:** Direct communication via `smbus2`, bypassing the unreliable `ti-ads1015` kernel driver.
- **Auto-reinstall:** Survives Venus OS firmware updates via SetupHelper/PackageManager.

---

## 📸 Screenshots

Tank sensors appear as native tank devices in Venus OS:

![Tank level sensors in Venus OS GUI](levels-gui-v2.png)

---

## 🛠 Hardware Setup

### Required Components

- ADS1115 16-bit ADC module
- 220 Ω resistor (one per sensor)
- Resistive level sensor (e.g. 0–190 Ω tank sensor)
- Jumper wires

### 1. ADS1115 → Raspberry Pi (I2C)

```text
      ADS1115 (ADC)                  Raspberry Pi 4 (GPIO)
    ┌───────────────┐               ┌──────────────────────────┐
(1) │      VDD      │◄─────────────►│ Pin 1  (3.3V Power)      │
(2) │      GND      │◄─────────────►│ Pin 6  (Ground)          │
(3) │      SCL      │◄─────────────►│ Pin 5  (SCL / GPIO 3)    │
(4) │      SDA      │◄─────────────►│ Pin 3  (SDA / GPIO 2)    │
(5) │      ADDR     │◄──────┐       │                          │
    │      ALRT     │ (N.C) │       └──────────────────────────┘
    └───────┬───────┘       └───────► Pin 9 (Ground)  → Address 0x48
```

### 2. Sensor Wiring (Voltage Divider)

Each resistive sensor requires a pull-up resistor to form a voltage divider. A 220 Ω resistor is recommended for standard tank sensors.

```text
 3.3V (Pin 1) ────┐
                  │
            [ 220 Ω ]          ← Fixed pull-up resistor
                  │
                  ├──────────► A0 on ADS1115
                  │
            [ TANK SENSOR ]    ← Resistive sensor (e.g. 0–190 Ω)
                  │
 GND  (Pin 9) ────┘
```

**How it works:** The resistor and sensor form a voltage divider. As the tank level changes, the sensor resistance changes. The ADS1115 measures the voltage at the midpoint; the driver converts this to a resistance and then to a percentage.

> [!CAUTION]
> **Voltage protection:** The ADS1115 analog inputs must not exceed 3.3 V. Never connect sensors directly to 12 V or 24 V lines without a proper voltage divider or level shifter.

**Notes:**
- Each sensor needs its own 220 Ω pull-up resistor
- Each sensor connects to a separate ADC channel (A0–A3)
- All sensors share the same 3.3 V and GND rails
- Up to 4 tanks per ADS1115 module

### Supported Sensor Standards

| Standard | Empty resistance | Full resistance | Typical use |
|----------|-----------------|----------------|-------------|
| European | 0 Ω | 180 Ω | Most EU tank sensors |
| US / NMEA | 240 Ω | 30 Ω | US marine / NMEA sensors |
| Custom | user-defined | user-defined | Any resistive sensor |

---

## 📥 Installation

### Prerequisites — Enable I2C

> [!IMPORTANT]
> I2C is **disabled by default** on Venus OS. Without it the ADS1115 cannot be read and all tanks will show **"Open Circuit"**.

The `setup` script enables I2C automatically. To verify manually via SSH:

```bash
# Scan I2C bus — ADS1115 should appear at address 0x48
i2cdetect -y 1

# Expected output:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 40: -- -- -- -- -- -- -- -- 48 -- -- -- -- -- -- --
```

| Requirement | Purpose |
|---|---|
| `dtparam=i2c_arm=on` in `/u-boot/config.txt` | Activates I2C GPIO pins — survives reboots and OTA updates |
| `i2c-dev` kernel module | Exposes `/dev/i2c-1` to userspace |
| `smbus2` Python library | Pure-Python I2C access — re-installed by `setup` on every firmware update |

If `/dev/i2c-1` is missing after running `setup`, re-run it or manually:

```bash
echo "dtparam=i2c_arm=on" >> /u-boot/config.txt
modprobe i2c-dev
reboot
```

> Venus OS on Raspberry Pi 4 mounts the boot partition at `/u-boot/`. The `setup` script checks `/u-boot/config.txt`, `/boot/config.txt`, and `/mnt/boot/config.txt` in order.

---

### Method 1: PackageManager (Recommended)

Requires [SetupHelper](https://github.com/kwindrem/SetupHelper) installed on your Venus OS device.

**Via GUI:**
1. Go to `Settings → PackageManager → Add package`
2. Enter:
   - Owner: `alexsanzder`
   - Repository: `dbus-ads1115`
   - Branch/Tag: `latest`
3. Click **Add** — the package installs automatically.

**Via SSH:**
```bash
wget -qO - https://github.com/alexsanzder/dbus-ads1115/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/dbus-ads1115
mv /data/dbus-ads1115-latest /data/dbus-ads1115
/data/dbus-ads1115/setup
```

**Via USB/SD card:**
Download the release archive from the [releases page](https://github.com/alexsanzder/dbus-ads1115/releases), copy it to the root of a USB stick or SD card, insert into the GX device and reboot.

### After Installation

1. Edit `/data/dbus-ads1115/config.yml` to match your sensor wiring and tank capacity.
2. Restart the service: `svc -t /service/dbus-ads1115`
3. The sensor appears in `Settings → Devices` within a few seconds.

### Automatic Reinstallation

When using PackageManager/SetupHelper, the driver reinstalls automatically after every Venus OS firmware update. No manual steps needed.

> **Your `config.yml` is preserved across updates.** The file is excluded from release tarballs, so PackageManager never overwrites it. On first install, `config.yml.example` is copied to `config.yml` if it doesn't already exist.

---

## ⚙️ Configuration (`config.yml`)

Edit `/data/dbus-ads1115/config.yml` to define your sensors.

```yaml
i2c:
  bus: 1
  address: 0x48
  reference_voltage: 3.3

sensors:
  # Fresh Water Tank — Channel A0
  - type: tank
    enabled: true
    name: "Fresh Water Tank"
    channel: 0
    fixed_resistor: 220        # Pull-up resistor in Ω
    sensor_min: 0.0            # Resistance at EMPTY in Ω (initial default)
    sensor_max: 190.0          # Resistance at FULL  in Ω (initial default)
    tank_capacity: 70          # Capacity in your chosen unit
    volume_unit: liters        # liters | cubic_meters | gallons_us | gallons_imp
    fluid_type: fresh_water
    update_interval: 3000      # ms between readings
    product_name: "A5-E225 (0-190Ω, 225mm)"
    product_id: 0xE225

  # Grey Water Tank — Channel A1
  - type: tank
    enabled: false             # Set to true when sensor is wired
    name: "Grey Water Tank"
    channel: 1
    fixed_resistor: 220
    sensor_min: 0.0
    sensor_max: 190.0
    tank_capacity: 70
    volume_unit: liters
    fluid_type: waste_water
    update_interval: 3000
    product_name: "A5-E125 (0-190Ω, 125mm)"
    product_id: 0xE125
```

### Configuration Parameters

| Parameter | Description |
|---|---|
| `enabled` | `false` disables the sensor entirely (no D-Bus service, no ADC read) |
| `name` | Display name shown in Venus OS |
| `channel` | ADS1115 input channel: `0`=A0, `1`=A1, `2`=A2, `3`=A3 |
| `fixed_resistor` | Pull-up resistor value in Ω (typically 220) |
| `pga` | Programmable Gain Amplifier full-scale voltage (default `2.048`) |
| `sensor_min` | **Resistance at EMPTY in Ω** — initial default; overridden by GUI or Standard preset |
| `sensor_max` | **Resistance at FULL in Ω** — initial default; overridden by GUI or Standard preset |
| `tank_capacity` | Capacity in the unit set by `volume_unit` |
| `volume_unit` | `liters` · `cubic_meters` · `gallons_us` · `gallons_imp` (default: `cubic_meters`) |
| `fluid_type` | See [Fluid Types](#fluid-types) |
| `update_interval` | Milliseconds between ADC reads |
| `product_name` | Device label shown in VRM Portal |
| `product_id` | Numeric product ID for VRM Portal (hex or int, e.g. `0xE225`) |

> **`sensor_min` / `sensor_max`** are the *initial* calibration values. After first install you can refine them live from the Venus OS GUI Setup page — changes persist in `com.victronenergy.settings` and survive service restarts.

> **Display units:** The driver stores capacity in m³ on D-Bus. The unit shown in the GUI is a system-wide setting at `Settings → System setup → Volume unit` (0 = m³, 1 = Liters, 2 = US gal, 3 = Imp gal).

### Per-Sensor Alarms

```yaml
alarms:
  low:
    enable: true
    active: 20       # Trigger when level < 20%
    restore: 25      # Clear when level > 25%
    delay: 30        # Seconds before triggering (prevents flapping)
  high:
    enable: true
    active: 90       # Trigger when level > 90%
    restore: 85      # Clear when level < 85%
    delay: 5
```

| Parameter | Description |
|---|---|
| `enable` | `true` to activate this alarm |
| `active` | Level % that triggers the alarm |
| `restore` | Level % that clears the alarm |
| `delay` | Seconds to wait before triggering |

### Fluid Types

| Key | Description |
|---|---|
| `fresh_water` | Fresh / potable water |
| `waste_water` | Grey water |
| `black_water` | Sewage |
| `fuel` | Generic fuel |
| `diesel` | Diesel |
| `gasoline` | Gasoline |
| `oil` | Motor oil |
| `hydraulic_oil` | Hydraulic oil |
| `live_well` | Live well (fishing boats) |
| `lng` | Liquefied Natural Gas |
| `lpg` | Liquefied Petroleum Gas |

---

## 🔧 Calibration

### Option A — `config.yml` (before first install)

1. Measure sensor resistance with a multimeter at **empty** → set `sensor_min`
2. Measure at **full** → set `sensor_max`
3. Restart: `svc -t /service/dbus-ads1115`

### Option B — Venus OS GUI (live, no SSH needed)

Navigate to `Settings → Devices → <Tank name> → Setup`:

| GUI field | D-Bus path | Description |
|---|---|---|
| Sensor value when empty | `/RawValueEmpty` | Resistance at empty in Ω |
| Sensor value when full | `/RawValueFull` | Resistance at full in Ω |
| Sensor value (live) | `/RawValue` | Current resistance in Ω (read-only) |

Changes save instantly and persist across restarts.

---

## 🎛 Venus OS GUI Setup

Every tank sensor exposes a full **Setup** page at `Settings → Devices → <Tank name> → Setup`.

### Wiring Standard Presets

| Value | Standard | Empty | Full |
|-------|----------|-------|------|
| 0 | **European** | 0 Ω | 180 Ω |
| 1 | **US / NMEA** | 240 Ω | 30 Ω |
| 2 | **Custom** | `sensor_min` | `sensor_max` |

Selecting European or US automatically updates the empty/full values. The default at first install is **Custom**.

### Custom Tank Shape

Non-linear tanks (cylindrical on their side, D-shaped hulls, cone-bottom) need a shape correction curve.

Go to `Setup → Custom shape` and enter up to **10 points** as `sensorLevel:volume` integer-percentage pairs:

```
10:5,50:40,80:90
```

| Point | Sensor reads | Actual volume |
|---|---|---|
| `10:5` | 10% | 5% |
| `50:40` | 50% | 40% |
| `80:90` | 80% | 90% |

The curve always passes through **0 % → 0 %** and **100 % → 100 %** implicitly. Leave the field empty for linear mapping (no correction).

---

## 📜 License

This project is released under the [MIT License](LICENSE).
