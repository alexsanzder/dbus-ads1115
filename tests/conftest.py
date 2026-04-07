"""
Pytest configuration and shared fixtures for dbus-ads1115 tests.
"""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_config():
    """Valid sensor configuration for testing."""
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
        'product_id': 0xA5225,  # Configurable product ID for VRM Portal
    }


@pytest.fixture
def mock_dbus():
    """Provide a simple mock object that behaves like a shared VeDbusService for tests.
    The tests only expect that indexing and .dbusconn exist in some cases; when a real
    dbus library is not available, return a lightweight mock.
    """
    svc = Mock()
    # provide a dbusconn attribute used by SettingsDevice
    svc.dbusconn = Mock()
    # Ensure __setitem__ and __getitem__ are present for code that writes to '/Level'
    svc.__setitem__ = Mock()
    svc.__getitem__ = Mock()
    return svc


import tempfile
import os


@pytest.fixture
def mock_config_file(tmp_path):
    content = '''
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Test Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
'''
    p = tmp_path / "config.yml"
    p.write_text(content)
    return str(p)


@pytest.fixture
def multi_sensor_config(tmp_path):
    content = '''
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Tank 1"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
  - type: tank
    name: "Tank 2"
    channel: 1
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.05
    fluid_type: waste_water
'''
    p = tmp_path / "config_multi.yml"
    p.write_text(content)
    return str(p)
