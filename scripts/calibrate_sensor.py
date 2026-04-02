#!/usr/bin/env python3
"""Calibration CLI for ADS1115 TankSensor

Usage: scripts/calibrate_sensor.py <config.yml> <sensor_index> <raw_empty> <raw_full> [--persist]

Examples:
  scripts/calibrate_sensor.py config.yml 0 1200 23000 --persist

This script loads the config, instantiates SensorManager to create sensors and a
shared VeDbusService, then computes scale/offset for the chosen sensor and
optionally persists them via the SettingsDevice API.
"""
import sys
import logging
from argparse import ArgumentParser

from dbus_ads1115.dbus_ads1115 import SensorManager


def main():
    p = ArgumentParser()
    p.add_argument('config')
    p.add_argument('sensor_index', type=int)
    p.add_argument('raw_empty', type=float)
    p.add_argument('raw_full', type=float)
    p.add_argument('--persist', action='store_true')
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO)

    manager = SensorManager(args.config)
    if args.sensor_index < 0 or args.sensor_index >= len(manager._sensors):
        print('Invalid sensor index')
        return 2

    sensor = manager._sensors[args.sensor_index]
    result = sensor.calibrate(args.raw_empty, args.raw_full, persist=args.persist)
    print('Calibration result:')
    print('  scale =', result['scale'])
    print('  offset =', result['offset'])

    if args.persist:
        print('Persisted to SettingsDevice (if available)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
