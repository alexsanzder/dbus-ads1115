#!/usr/bin/env python3
"""Interactive calibration helper for ADS1115 tank sensors.

Usage:
  scripts/interactive_calibrate.py <config.yml> [--sensor INDEX] [--samples N] [--delay SEC] [--persist]

The script will load the config, list sensors, let you select one (or pass --sensor),
then prompt you to place the sensor in the EMPTY position and press Enter to sample,
then in the FULL position and press Enter to sample. It computes scale/offset and
optionally persists them via the driver's SettingsDevice.

This is intended to be run on the target device (VenusOS) where the driver can
access /sys and the system D-Bus. In test environments it will still run but the
persist option may be a no-op if the settings API isn't available.
"""
from __future__ import annotations
import argparse
import time
import os
import sys
import math

from dbus_ads1115.dbus_ads1115 import SensorManager


def avg_raw(sysfs_path: str, samples: int = 20, delay: float = 0.05) -> float:
    vals = []
    for i in range(samples):
        with open(sysfs_path, 'r') as f:
            vals.append(int(f.read().strip()))
        time.sleep(delay)
    return sum(vals) / len(vals)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('config')
    p.add_argument('--sensor', '-s', type=int, default=None,
                   help='Sensor index (0-based) to calibrate')
    p.add_argument('--samples', type=int, default=20, help='Samples to average')
    p.add_argument('--delay', type=float, default=0.05, help='Delay between samples (s)')
    p.add_argument('--persist', action='store_true', help='Persist scale/offset to settings')
    args = p.parse_args()

    if not os.path.exists(args.config):
        print('Config file not found:', args.config)
        return 2

    manager = SensorManager(args.config)
    if len(manager._sensors) == 0:
        print('No sensors found in configuration')
        return 1

    print('\nDetected sensors:')
    for idx, s in enumerate(manager._sensors):
        name = getattr(s, '_name', None) or f'Sensor {idx}'
        path = getattr(s, '_sysfs_path', 'N/A')
        print(f'  [{idx}] {name} -> {path}')

    idx = args.sensor
    if idx is None:
        idx = int(input('\nEnter sensor index to calibrate: '))

    if idx < 0 or idx >= len(manager._sensors):
        print('Invalid sensor index')
        return 2

    sensor = manager._sensors[idx]
    sysfs = getattr(sensor, '_sysfs_path', None)
    if not sysfs or not os.path.exists(sysfs):
        print('Warning: sysfs path not found for sensor:', sysfs)
        print('You may still proceed by entering a custom sysfs path or abort.')
        custom = input('Enter sysfs path or leave empty to abort: ').strip()
        if not custom:
            return 1
        sysfs = custom

    print('\nSampling parameters: samples=%d delay=%.3fs' % (args.samples, args.delay))

    input('\nPlace sensor in EMPTY position (or known low volume) and press Enter to sample...')
    print('Sampling EMPTY...')
    raw_empty = avg_raw(sysfs, samples=args.samples, delay=args.delay)
    print(f'  AVG RAW EMPTY = {raw_empty:.3f}')

    input('\nPlace sensor in FULL position (or known high volume) and press Enter to sample...')
    print('Sampling FULL...')
    raw_full = avg_raw(sysfs, samples=args.samples, delay=args.delay)
    print(f'  AVG RAW FULL  = {raw_full:.3f}')

    print('\nComputing calibration parameters...')
    try:
        res = sensor.calibrate(raw_empty, raw_full, persist=False)
    except Exception as e:
        print('Calibration failed:', e)
        return 1

    print('\nCalibration result:')
    print('  scale  =', res['scale'])
    print('  offset =', res['offset'])

    if args.persist:
        try:
            sensor.calibrate(raw_empty, raw_full, persist=True)
            print('Persisted calibration to settings (if available)')
        except Exception as e:
            print('Failed to persist calibration:', e)

    print('\nYou can verify by placing the sensor at intermediate positions and running:')
    print(f'  cat {sysfs}  # raw sample')
    print('Or use the driver GUI / D-Bus to see Level/Remaining for this device.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
