#!/usr/bin/python3 -u
import sys
import os
import re
import logging
from datetime import datetime
from argparse import ArgumentParser

# Configure logging at the top to catch all initialization messages
parser = ArgumentParser(description='dbus-ads1115')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
parser.add_argument('-c', '--config', default='config.yml', help='Path to config file')
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

# Internal YAML Parser (for systems without PyYAML)
def parse_simple_yaml(content):
    def parse_value(v):
        v = v.strip()
        if v.lower() == 'true': return True
        if v.lower() == 'false': return False
        try: return int(v)
        except ValueError:
            try: return float(v)
            except ValueError: return v.strip('"\'')

    config = {}
    stack = [(None, config)]
    for line in content.split('\n'):
        line = line.split('#')[0].rstrip()
        if not line: continue
        indent = len(line) - len(line.lstrip())
        level = indent // 2
        stripped = line.strip()
        while len(stack) > level + 1: stack.pop()
        _, current = stack[-1]
        
        m = re.match(r'^(\w+)\s*:\s*$', stripped)
        if m:
            name = m.group(1)
            current[name] = [] if name == 'sensors' else {}
            stack.append((name, current[name]))
            continue
            
        m = re.match(r'^-\s*(\w+)\s*:\s*(.*)$', stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            item = {key: parse_value(val)} if val else {key: {}}
            current.append(item)
            stack.append((key, item))
            continue
            
        m = re.match(r'^(\w+)\s*:\s*(.*)$', stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            current[key] = parse_value(val) if val else {}
    return config

class yaml_fallback:
    @staticmethod
    def safe_load(stream):
        return parse_simple_yaml(stream.read())

try:
    import yaml
except ImportError:
    yaml = yaml_fallback

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from dbus_ads1115.sensors import TankSensor
from dbus_ads1115.vedbus import VeDbusService

logger = logging.getLogger(__name__)
VERSION = '1.0.0'

class SensorManager:
    def __init__(self, config_filename):
        with open(config_filename, "r") as stream:
            try:
                self._config = yaml.safe_load(stream)
            except Exception:
                # Malformed YAML or other read error: fall back to empty config
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

        for cfg in sensors_cfg:
            cfg['i2c_bus'] = cfg.get('i2c_bus', i2c_cfg.get('bus', 1))
            cfg['i2c_address'] = cfg.get('i2c_address', i2c_cfg.get('address', '0x48'))
            cfg['reference_voltage'] = i2c_cfg.get('reference_voltage', 3.3)
            # Pass channel_map from i2c config to sensor
            cfg['channel_map'] = i2c_cfg.get('channel_map', [0, 1, 2, 3])

            if cfg.get('type') == 'tank':
                # Each sensor creates its own D-Bus service (dbus=None means create new service)
                self._sensors.append(TankSensor(cfg, dbus=None))

    def update(self):
        import time
        for s in self._sensors:
            try:
                s.update()
            except Exception:
                logging.exception("Sensor update failed, continuing with next sensor")
            # ADS1015 kernel driver needs time to settle when switching channels.
            # Without this delay, rapid successive reads from different channels
            # can return incorrect values due to mux settling time.
            time.sleep(0.1)  # 100ms delay between sensor reads
        return True

def main():
    # Args already partially parsed for logging setup, but re-parse fully for completeness
    args = parser.parse_args()

    logger.info(f'Starting dbus-ads1115 v{VERSION}')

    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    manager = SensorManager(args.config)
    GLib.timeout_add(5000, manager.update)
    
    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
