"""
Pytest configuration and shared fixtures for dbus-ads1115 tests.
"""

import os
import sys
import tempfile
from unittest.mock import Mock, MagicMock, patch
import pytest

# Mock dbus module for macOS compatibility
sys.modules['dbus'] = Mock()
sys.modules['dbus.service'] = Mock()
sys.modules['dbus.mainloop'] = Mock()
sys.modules['dbus.mainloop.glib'] = Mock()
sys.modules['gi'] = Mock()
sys.modules['gi.repository'] = Mock()

# Mock vedbus module
sys.modules['dbus_ads1115.vedbus'] = Mock()
sys.modules['dbus_ads1115.settingsdevice'] = Mock()


@pytest.fixture
def mock_dbus():
    """Mock D-Bus connection and service."""
    mock_conn = Mock()
    yield mock_conn


@pytest.fixture
def mock_glib():
    """Mock GLib main loop."""
    mock_glib = Mock()
    yield mock_glib


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


@pytest.fixture
def mock_config_file(mock_config):
    """Create temporary config file for testing."""
    config_content = f"""
# Test configuration
i2c:
  bus: {mock_config['i2c_bus']}
  address: "{mock_config['i2c_address']}"
  reference_voltage: {mock_config['reference_voltage']}

sensors:
  - type: {mock_config['type']}
    name: "{mock_config['name']}"
    channel: {mock_config['channel']}
    fixed_resistor: {mock_config['fixed_resistor']}
    sensor_min: {mock_config['sensor_min']}
    sensor_max: {mock_config['sensor_max']}
    tank_capacity: {mock_config['tank_capacity']}
    fluid_type: {mock_config['fluid_type']}
    update_interval: 5000
"""
    fd, path = tempfile.mkstemp(suffix='.yml', text=True)
    with os.fdopen(fd, 'w') as f:
        f.write(config_content)
    yield path
    os.unlink(path)


@pytest.fixture
def mock_i2c_device(mock_config):
    """Mock I2C sysfs device for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        i2c_path = os.path.join(tmpdir, f"i2c-{mock_config['i2c_bus']}")
        os.makedirs(i2c_path)
        
        device_path = os.path.join(i2c_path, f"00{mock_config['i2c_address'][2:]}")
        os.makedirs(device_path)
        
        iio_path = os.path.join(device_path, "iio:device0")
        os.makedirs(iio_path)
        
        voltage_path = os.path.join(iio_path, f"in_voltage{mock_config['channel']}_raw")
        with open(voltage_path, 'w') as f:
            f.write("1000")
        
        with patch('os.path.exists') as mock_exists:
            # Make sysfs paths exist in our temp directory
            def exists_side_effect(path):
                if 'i2c' in path or 'iio' in path:
                    return path.replace('/', os.sep) in [
                        i2c_path.replace('/', os.sep),
                        device_path.replace('/', os.sep),
                        iio_path.replace('/', os.sep),
                        voltage_path.replace('/', os.sep)
                    ]
                return os.path.exists(path)
            mock_exists.side_effect = exists_side_effect
            
            with patch('builtins.open') as mock_open:
                # Mock file reading from our temp directory
                def open_side_effect(path, mode='r'):
                    if 'in_voltage' in str(path):
                        return open(voltage_path, mode)
                    raise FileNotFoundError(f"No mock for {path}")
                mock_open.side_effect = open_side_effect
                yield voltage_path


@pytest.fixture
def minimal_config():
    """Minimal sensor config (tests defaults)."""
    return {
        'type': 'tank',
        'name': 'Minimal Tank',
        'channel': 0,
        'fixed_resistor': 220,
        'sensor_min': 0.0,
        'sensor_max': 10.0,
        'tank_capacity': 0.05
    }


@pytest.fixture
def invalid_config():
    """Invalid sensor configuration for error testing."""
    return {
        'type': 'tank',
        # Missing required fields
        'name': 'Invalid Tank'
    }


@pytest.fixture
def multi_sensor_config():
    """Configuration with multiple sensors."""
    return {
        'i2c': {
            'bus': 1,
            'address': '0x48',
            'reference_voltage': 3.3
        },
        'sensors': [
            {
                'type': 'tank',
                'name': 'Tank 1',
                'channel': 0,
                'fixed_resistor': 220,
                'sensor_min': 0.1,
                'sensor_max': 13.55,
                'tank_capacity': 0.07,
                'fluid_type': 'fresh_water'
            },
            {
                'type': 'tank',
                'name': 'Tank 2',
                'channel': 1,
                'fixed_resistor': 220,
                'sensor_min': 0.1,
                'sensor_max': 13.55,
                'tank_capacity': 0.05,
                'fluid_type': 'waste_water'
            }
        ]
    }
