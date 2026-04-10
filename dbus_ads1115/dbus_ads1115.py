#!/usr/bin/python3 -u
import sys
import os
import configparser
import logging
from argparse import ArgumentParser

# Configure logging at the top to catch all initialization messages
parser = ArgumentParser(description='dbus-ads1115')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
parser.add_argument('-c', '--config', default='config.ini', help='Path to user config file (default: config.ini). Layered on top of config.default.ini.')
# Use a temporary parse to get log level before full initialization
temp_args, _ = parser.parse_known_args()
logging.basicConfig(level=(logging.DEBUG if temp_args.debug else logging.INFO),
                    format='%(levelname)-8s %(message)s')

try:
    import dbus
    import dbus.mainloop.glib
except Exception:
    # Provide minimal dbus compatibility in test environments where the
    # system 'dbus' package is not available.
    import types
    dbus = types.SimpleNamespace()
    dbus.mainloop = types.SimpleNamespace(glib=types.SimpleNamespace())
try:
    from gi.repository import GLib
except Exception:
    # Minimal GLib stub for test environments where gi is not available.
    class _StubGLib:
        @staticmethod
        def timeout_add(interval, func, *args, **kwargs):
            # We won't schedule anything in tests; return a dummy id
            return 0

        class MainLoop:
            def __init__(self):
                pass

            def run(self):
                return

            def quit(self):
                return

    GLib = _StubGLib()

# ---------------------------------------------------------------------------
# Config loader — INI format (configparser), layered:
#   config.default.ini  — shipped with the package (all keys + defaults)
#   config.ini          — user overrides (preserved across updates)
#
# Following the convention established by dbus-serialbattery and other
# popular Venus OS community drivers.
# ---------------------------------------------------------------------------

SENSOR_SECTIONS = [f'sensor{i}' for i in range(4)]  # sensor0 … sensor3

def _load_config(user_config_path: str) -> dict:
    """
    Parse the layered INI config and return a normalised dict that the rest
    of the code can consume without knowing it came from configparser.

    Structure returned:
        {
            'i2c': { 'bus': 1, 'address': '0x48', 'reference_voltage': 3.3 },
            'sensors': [
                { 'type': 'tank', 'name': '...', 'channel': 0, ... },
                ...
            ]
        }
    """
    cfg = configparser.ConfigParser(
        # Keep keys case-sensitive (product_name, etc.)
        # configparser lower-cases by default — override that
        inline_comment_prefixes=(';', '#'),
        comment_prefixes=(';', '#'),
        strict=True,
    )
    cfg.optionxform = str  # preserve key case

    # Locate config.default.ini relative to this file
    _here = os.path.dirname(os.path.abspath(__file__))
    _pkg_root = os.path.dirname(_here)
    default_ini = os.path.join(_pkg_root, 'config.default.ini')

    files_read = cfg.read([default_ini, user_config_path])
    if not files_read:
        raise FileNotFoundError(
            f"No config files found. Looked for:\n  {default_ini}\n  {user_config_path}"
        )

    def _bool(val: str) -> bool:
        return val.strip().lower() in ('true', '1', 'yes', 'on')

    def _auto(val: str):
        """Cast string to int / float / bool / str automatically."""
        v = val.strip()
        if v.lower() in ('true', 'yes', 'on'):  return True
        if v.lower() in ('false', 'no', 'off'): return False
        try:   return int(v, 0)          # handles 0x48 hex literals
        except ValueError: pass
        try:   return float(v)
        except ValueError: pass
        return v

    # --- i2c section ---
    i2c = {}
    if cfg.has_section('i2c'):
        for k, v in cfg.items('i2c'):
            i2c[k] = _auto(v)

    # --- sensor sections ---
    sensors = []
    for section in SENSOR_SECTIONS:
        if not cfg.has_section(section):
            continue
        raw = dict(cfg.items(section))
        if not _bool(raw.get('enabled', 'true')):
            continue

        sensor = {k: _auto(v) for k, v in raw.items()}

        # Flatten alarm keys:  alarm_low_enable → alarms.low.enable
        alarms = {}
        for level in ('low', 'high'):
            entry = {}
            for field in ('enable', 'active', 'restore', 'delay'):
                key = f'alarm_{level}_{field}'
                if key in sensor:
                    entry[field] = sensor.pop(key)
            if entry:
                alarms[level] = entry
        if alarms:
            sensor['alarms'] = alarms

        sensors.append(sensor)

    return {'i2c': i2c, 'sensors': sensors}

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from dbus_ads1115.sensors import TankSensor
from dbus_ads1115.vedbus import VeDbusService

logger = logging.getLogger(__name__)

try:
    from dbus_ads1115 import __version__ as VERSION
except ImportError:
    VERSION = '0.0.0'  # Safety fallback – should never be reached in a proper install

class SensorManager:
    def __init__(self, config_filename):
        try:
            self._config = _load_config(config_filename)
        except Exception:
            logging.exception("Failed to parse config file, using empty config")
            self._config = {}
        self._sensors = []
        self._create_sensors()

    def _create_sensors(self):
        sensors_cfg = self._config.get('sensors') or []
        i2c_cfg = self._config.get('i2c', {})
        # Each TankSensor creates its own VeDbusService with root-level paths.
        # Venus OS requires each tank to be its own D-Bus service for device list detection.
        # Service names will be: com.victronenergy.tank.ads1115_0, com.victronenergy.tank.ads1115_1, etc.

        for idx, cfg in enumerate(sensors_cfg):
            cfg['i2c_bus'] = cfg.get('i2c_bus', i2c_cfg.get('bus', 1))
            cfg['i2c_address'] = cfg.get('i2c_address', i2c_cfg.get('address', '0x48'))
            cfg['reference_voltage'] = i2c_cfg.get('reference_voltage', 3.3)
            # Pass channel_map from i2c config to sensor
            cfg['channel_map'] = i2c_cfg.get('channel_map', [0, 1, 2, 3])

            if cfg.get('type') == 'tank' and cfg.get('enabled', True):
                sensor = TankSensor(cfg, dbus=None)
                self._sensors.append(sensor)

                # Per-sensor update timer – honours update_interval from config.
                # Stagger the first read by 200 ms per sensor index so that two
                # sensors on the same I2C bus are never accessed simultaneously
                # at boot (important for SMBus MUX settling).
                interval = int(cfg.get('update_interval', 5000))
                boot_delay = 500 + idx * 200
                GLib.timeout_add(boot_delay, self._make_first_update(sensor, interval))
                logging.info(
                    f"Sensor '{cfg.get('name', f'tank_{idx}')}': "
                    f"first read in {boot_delay} ms, then every {interval} ms"
                )
            elif cfg.get('type') == 'tank' and not cfg.get('enabled', True):
                logging.info(
                    f"Sensor '{cfg.get('name', f'tank_{idx}')}': skipped (enabled: false)"
                )

    def _make_first_update(self, sensor, interval):
        """One-shot GLib callback: reads the sensor once, then arms the recurring timer."""
        def _first():
            try:
                sensor.update()
            except Exception:
                logging.exception("Sensor first update failed")
            GLib.timeout_add(interval, self._make_recurring_update(sensor))
            return False  # Do not re-arm this callback
        return _first

    def _make_recurring_update(self, sensor):
        """Recurring GLib callback for a single sensor – returns True to keep firing."""
        def _cb():
            try:
                sensor.update()
            except Exception:
                logging.exception("Sensor update failed")
            return True
        return _cb

    def update(self):
        """Update all sensors synchronously.

        Retained for backward-compatibility (e.g. test suites that call it
        directly).  In production the per-sensor GLib timers registered in
        _create_sensors() drive all updates; this method is NOT called from
        main() and does NOT block the event loop.
        """
        for s in self._sensors:
            try:
                s.update()
            except Exception:
                logging.exception("Sensor update failed, continuing with next sensor")
        return True

def main():
    # Args already partially parsed for logging setup, but re-parse fully for completeness
    args = parser.parse_args()

    logger.info(f'Starting dbus-ads1115 v{VERSION}')

    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    manager = SensorManager(args.config)
    # Per-sensor update timers are registered inside SensorManager._create_sensors().
    # No global timer is needed here.
    
    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
