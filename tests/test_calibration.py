import pytest
from dbus_ads1115.sensors import TankSensor


def test_calibration_basic(mock_config, mock_dbus):
    # Create a sensor with known config and mock dbus
    sensor = TankSensor(mock_config, dbus=mock_dbus)

    # Choose synthetic raw measurements that produce a sensible scale/offset
    raw_empty = 1000.0
    raw_full = 20000.0

    res = sensor.calibrate(raw_empty, raw_full)

    assert 'scale' in res and 'offset' in res
    assert isinstance(res['scale'], float)
    assert isinstance(res['offset'], float)
