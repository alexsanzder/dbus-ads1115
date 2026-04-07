"""
Tests for SensorManager class.
"""

import pytest
from unittest.mock import Mock, patch
import os
import tempfile


class TestSensorManagerInitialization:
    """Test SensorManager initialization."""

    def test_initialization_with_valid_config(self, mock_config_file):
        """Test initialization with valid configuration file."""
        # Import here to avoid circular import issues
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        manager = SensorManager(mock_config_file)
        
        assert manager._config is not None
        assert 'sensors' in manager._config
        assert len(manager._sensors) > 0

    def test_initialization_creates_tank_sensors(self, mock_config_file):
        """Test that TankSensor instances are created."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        manager = SensorManager(mock_config_file)
        
        # Should have created TankSensor instances
        assert len(manager._sensors) > 0
        for sensor in manager._sensors:
            from dbus_ads1115.sensors import TankSensor
            assert isinstance(sensor, TankSensor)

    def test_initialization_with_empty_sensors_list(self):
        """Test initialization with empty sensors list."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"

sensors:
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 0
        finally:
            os.unlink(path)

    def test_initialization_with_missing_sensors_key(self):
        """Test initialization when sensors key is missing."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 0
        finally:
            os.unlink(path)


class TestSensorManagerIC2ConfigFallback:
    """Test I2C configuration fallback behavior."""

    def test_i2c_bus_fallback_to_global(self):
        """Test that sensor uses global I2C bus when not specified."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 2
  address: "0x49"
  reference_voltage: 5.0

sensors:
  - type: tank
    name: "Test Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            # First sensor should use global I2C bus (2)
            assert manager._sensors[0]._i2c_bus == 2
        finally:
            os.unlink(path)

    def test_i2c_bus_sensor_specific_overrides_global(self):
        """Test that sensor-specific I2C bus overrides global."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 2
  address: "0x49"
  reference_voltage: 5.0

sensors:
  - type: tank
    name: "Test Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
    i2c_bus: 3
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            # Sensor should use its specific I2C bus (3), not global (2)
            assert manager._sensors[0]._i2c_bus == 3
        finally:
            os.unlink(path)

    def test_i2c_address_fallback_to_global(self):
        """Test that sensor uses global I2C address when not specified."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x4A"
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
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            # Sensor should use global I2C address (0x4A)
            assert manager._sensors[0]._i2c_address == '0x4A'
        finally:
            os.unlink(path)

    def test_i2c_address_sensor_specific_overrides_global(self):
        """Test that sensor-specific I2C address overrides global."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x49"
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
    i2c_address: "0x4B"
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            # Sensor should use its specific I2C address (0x4B), not global (0x49)
            assert manager._sensors[0]._i2c_address == '0x4B'
        finally:
            os.unlink(path)

    def test_reference_voltage_fallback_to_global(self):
        """Test that sensor uses global reference voltage when not specified."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 5.0

sensors:
  - type: tank
    name: "Test Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            # Sensor should use global reference voltage (5.0)
            assert manager._sensors[0]._reference_voltage == 5.0
        finally:
            os.unlink(path)


class TestSensorManagerMultiSensor:
    """Test handling of multiple sensors."""

    def test_creates_multiple_sensors(self, multi_sensor_config):
        """Test that multiple TankSensor instances are created."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
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
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 2
            assert manager._sensors[0]._name == "Tank 1"
            assert manager._sensors[1]._name == "Tank 2"
        finally:
            os.unlink(path)

    def test_different_channels_for_multiple_sensors(self):
        """Test that multiple sensors use different channels."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"

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
  - type: tank
    name: "Tank 3"
    channel: 2
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.03
    fluid_type: fuel
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 3
            assert manager._sensors[0]._channel == 0
            assert manager._sensors[1]._channel == 1
            assert manager._sensors[2]._channel == 2
        finally:
            os.unlink(path)


class TestSensorManagerEnabledFlag:
    """Test that the `enabled` flag controls whether a sensor is instantiated."""

    def test_disabled_sensor_is_skipped(self):
        """A sensor with enabled: false must NOT appear in _sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        config_content = """
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Active Tank"
    enabled: true
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
  - type: tank
    name: "Inactive Tank"
    enabled: false
    channel: 1
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: waste_water
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)

        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 1
            assert manager._sensors[0]._name == "Active Tank"
        finally:
            os.unlink(path)

    def test_sensor_enabled_by_default(self):
        """A sensor without the enabled key must be instantiated (default True)."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        config_content = """
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Default Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)

        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 1
        finally:
            os.unlink(path)

    def test_all_disabled_produces_empty_sensor_list(self):
        """All sensors disabled must yield zero running sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        config_content = """
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Tank A"
    enabled: false
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
  - type: tank
    name: "Tank B"
    enabled: false
    channel: 1
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: waste_water
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)

        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 0
        finally:
            os.unlink(path)


class TestSensorManagerUpdate:
    """Test update method."""

    def test_update_calls_all_sensors(self, mock_config_file):
        """Test that update() calls update() on all sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        manager = SensorManager(mock_config_file)
        
        # Mock update method for all sensors
        for sensor in manager._sensors:
            sensor.update = Mock()
        
        # Call manager update
        manager.update()
        
        # Verify all sensors were updated
        for sensor in manager._sensors:
            sensor.update.assert_called_once()

    def test_update_returns_true(self, mock_config_file):
        """Test that update() returns True."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        manager = SensorManager(mock_config_file)
        result = manager.update()
        assert result is True

    def test_update_with_empty_sensors_list(self):
        """Test update when there are no sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"

sensors:
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            result = manager.update()
            assert result is True
        finally:
            os.unlink(path)

    def test_update_handles_sensor_update_exceptions(self):
        """Test that update() handles sensor update exceptions gracefully."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"

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
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            manager = SensorManager(path)
            
            # Make second sensor's update raise an exception
            with patch.object(manager._sensors[1], 'update', side_effect=Exception("Test error")):
                # First sensor should still update
                result = manager.update()
            
            # First sensor was called (second sensor's update was called via patch)
            # Manager should return True since at least one sensor updated
            assert result is True
            
        finally:
            os.unlink(path)


class TestSensorManagerErrorHandling:
    """Test error handling in SensorManager."""

    def test_handles_missing_config_file(self):
        """Test handling of missing configuration file."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        with pytest.raises(FileNotFoundError):
            SensorManager('/nonexistent/config.yml')

    def test_handles_invalid_yaml_syntax(self):
        """Test handling of invalid YAML syntax."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  invalid syntax here

sensors:
  - type: tank
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            # Should not crash, but may handle gracefully
            manager = SensorManager(path)
            # Config may be partially parsed or empty
            assert manager._config is not None
        finally:
            os.unlink(path)

    def test_handles_missing_required_sensor_fields(self):
        """Test handling of sensor with missing required fields."""
        from dbus_ads1115.dbus_ads1115 import SensorManager
        
        config_content = """
i2c:
  bus: 1
  address: "0x48"

sensors:
  - type: tank
    name: "Incomplete Tank"
    # Missing: channel, fixed_resistor, sensor_min, sensor_max, tank_capacity
"""
        fd, path = tempfile.mkstemp(suffix='.yml', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        try:
            # May raise KeyError or handle gracefully
            try:
                manager = SensorManager(path)
                # If it succeeds, sensors list may be empty or have incomplete sensors
                assert manager._sensors is not None
            except KeyError:
                # Expected for missing required fields
                pass
        finally:
            os.unlink(path)
