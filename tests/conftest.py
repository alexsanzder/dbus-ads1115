"""
Pytest configuration and shared fixtures for dbus-ads1115 tests.
"""

import pytest


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
        'reference_voltage': 3.3
    }
