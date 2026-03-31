#!/usr/bin/python3 -u
import sys
import os
import re
import logging
import dbus
import dbus.mainloop.glib
from datetime import datetime
from argparse import ArgumentParser
from gi.repository import GLib

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

logger = logging.getLogger(__name__)
VERSION = '1.0.0'

class SensorManager:
    def __init__(self, config_filename):
        with open(config_filename, "r") as stream:
            self._config = yaml.safe_load(stream)
        self._sensors = []
        self._create_sensors()

    def _create_sensors(self):
        sensors_cfg = self._config.get('sensors', [])
        i2c_cfg = self._config.get('i2c', {})
        
        for cfg in sensors_cfg:
            cfg['i2c_bus'] = cfg.get('i2c_bus', i2c_cfg.get('bus', 1))
            cfg['i2c_address'] = cfg.get('i2c_address', i2c_cfg.get('address', '0x48'))
            cfg['reference_voltage'] = i2c_cfg.get('reference_voltage', 3.3)
            
            if cfg.get('type') == 'tank':
                self._sensors.append(TankSensor(cfg))

    def update(self):
        for s in self._sensors:
            s.update()
        return True

def main():
    parser = ArgumentParser(description='dbus-ads1115')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-c', '--config', default='config.yml')
    args = parser.parse_args()

    logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO),
                        format='%(levelname)-8s %(message)s')
    
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
