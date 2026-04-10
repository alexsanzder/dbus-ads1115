"""
Pytest configuration and shared fixtures for dbus-ads1115 tests.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock


@pytest.fixture
def mock_config():
    """Valid sensor configuration dict for testing (no file needed)."""
    return {
        'type': 'tank',
        'name': 'Test Tank',
        'channel': 0,
        'fixed_resistor': 220,
        'sensor_min': 0.1,
        'sensor_max': 13.55,
        'tank_capacity': 0.07,
        'fluid_type': 'fresh_water',
        'i2c_bus': 1,
        'i2c_address': '0x48',
        'reference_voltage': 3.3,
        'product_id': 0xA5225,
    }


@pytest.fixture
def mock_dbus():
    """Lightweight mock of a shared VeDbusService for unit tests."""
    svc = Mock()
    svc.dbusconn = Mock()
    svc.__setitem__ = Mock()
    svc.__getitem__ = Mock()
    return svc


# ---------------------------------------------------------------------------
# INI config file helpers
# ---------------------------------------------------------------------------

_INI_I2C = """\
[i2c]
bus               = 1
address           = 0x48
reference_voltage = 3.3
"""

_INI_SENSOR0_MINIMAL = """\
[sensor0]
type           = tank
name           = Test Tank
channel        = 0
fixed_resistor = 220
sensor_min     = 0.1
sensor_max     = 13.55
tank_capacity  = 0.07
fluid_type     = fresh_water
"""

_INI_SENSOR1_MINIMAL = """\
[sensor1]
type           = tank
name           = Tank 2
channel        = 1
fixed_resistor = 220
sensor_min     = 0.1
sensor_max     = 13.55
tank_capacity  = 0.05
fluid_type     = waste_water
"""


def _write_ini(tmp_path, content: str, filename: str = "config.ini") -> str:
    """Write an INI string to a temp file and return its path."""
    p = tmp_path / filename
    p.write_text(content)
    return str(p)


@pytest.fixture
def mock_config_file(tmp_path):
    """Single-sensor INI config file."""
    return _write_ini(tmp_path, _INI_I2C + _INI_SENSOR0_MINIMAL)


@pytest.fixture
def multi_sensor_config(tmp_path):
    """Two-sensor INI config file."""
    return _write_ini(
        tmp_path,
        _INI_I2C + _INI_SENSOR0_MINIMAL + _INI_SENSOR1_MINIMAL,
        filename="config_multi.ini",
    )
