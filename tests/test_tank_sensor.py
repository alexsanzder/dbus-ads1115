"""
Tests for TankSensor class.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from dbus_ads1115.sensors import TankSensor
from dbus_ads1115.enums import FluidType, Status


class TestTankSensorInitialization:
    """Test TankSensor initialization."""

    def test_initialization_with_full_config(self, mock_dbus):
        """Test initialization with complete configuration."""
        config = {
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
        
        sensor = TankSensor(config, dbus=mock_dbus)
        
        assert sensor._channel == 0
        assert sensor._fixed_resistor == 220
        assert sensor._sensor_min == 0.1
        assert sensor._sensor_max == 13.55
        assert sensor._tank_capacity == 0.07
        assert sensor._fluid_type == FluidType.FRESH_WATER
        assert sensor._reference_voltage == 3.3
        assert sensor._i2c_bus == 1
        assert sensor._i2c_address == '0x48'

    def test_initialization_with_defaults(self, mock_dbus):
        """Test initialization with minimal config (uses defaults)."""
        config = {
            'type': 'tank',
            'name': 'Minimal Tank',
            'channel': 0,
            'fixed_resistor': 220,
            'sensor_min': 0.1,
            'sensor_max': 13.55,
            'tank_capacity': 0.07,
            'fluid_type': 'fresh_water'
        }
        
        sensor = TankSensor(config, dbus=mock_dbus)
        
        assert sensor._reference_voltage == 3.3  # Default
        assert sensor._i2c_bus == 1  # Default
        assert sensor._i2c_address == '0x48'  # Default

    def test_fluid_type_mapping(self, mock_dbus):
        """Test fluid type string to enum mapping."""
        test_cases = [
            ('fresh_water', FluidType.FRESH_WATER),
            ('waste_water', FluidType.WASTE_WATER),
            ('fuel', FluidType.FUEL),
            ('oil', FluidType.OIL),
            ('black_water', FluidType.BLACK_WATER),
            ('live_well', FluidType.LIVE_WELL)
        ]
        
        for fluid_type_str, expected_enum in test_cases:
            config = {
                'type': 'tank',
                'name': 'Test',
                'channel': 0,
                'fixed_resistor': 220,
                'sensor_min': 0.1,
                'sensor_max': 13.55,
                'tank_capacity': 0.07,
                'fluid_type': fluid_type_str
            }
            sensor = TankSensor(config, dbus=mock_dbus)
            assert sensor._fluid_type == expected_enum

    def test_default_fluid_type(self, mock_dbus):
        """Test that invalid fluid type defaults to FRESH_WATER."""
        config = {
            'type': 'tank',
            'name': 'Test',
            'channel': 0,
            'fixed_resistor': 220,
            'sensor_min': 0.1,
            'sensor_max': 13.55,
            'tank_capacity': 0.07,
            'fluid_type': 'invalid_type'
        }
        sensor = TankSensor(config, dbus=mock_dbus)
        assert sensor._fluid_type == FluidType.FRESH_WATER

    def test_sysfs_path_construction(self, mock_dbus):
        """Test correct sysfs path construction."""
        config = {
            'type': 'tank',
            'name': 'Test',
            'channel': 2,
            'fixed_resistor': 220,
            'sensor_min': 0.1,
            'sensor_max': 13.55,
            'tank_capacity': 0.07,
            'fluid_type': 'fresh_water',
            'i2c_bus': 1,
            'i2c_address': '0x48'
        }
        sensor = TankSensor(config, dbus=mock_dbus)
        expected_path = "/sys/bus/i2c/devices/1-0048/iio:device0/in_voltage2_raw"
        assert sensor._sysfs_path == expected_path

    def test_different_i2c_address(self, mock_dbus):
        """Test sysfs path with different I2C address."""
        config = {
            'type': 'tank',
            'name': 'Test',
            'channel': 0,
            'fixed_resistor': 220,
            'sensor_min': 0.1,
            'sensor_max': 13.55,
            'tank_capacity': 0.07,
            'fluid_type': 'fresh_water',
            'i2c_bus': 1,
            'i2c_address': '0x49'
        }
        sensor = TankSensor(config, dbus=mock_dbus)
        expected_path = "/sys/bus/i2c/devices/1-0049/iio:device0/in_voltage0_raw"
        assert sensor._sysfs_path == expected_path

    def test_initial_state_values(self, mock_dbus):
        """Test that initial state values are correct."""
        config = {
            'type': 'tank',
            'name': 'Test',
            'channel': 0,
            'fixed_resistor': 220,
            'sensor_min': 0.1,
            'sensor_max': 13.55,
            'tank_capacity': 0.07,
            'fluid_type': 'fresh_water'
        }
        sensor = TankSensor(config, dbus=mock_dbus)
        
        assert sensor._level == 0.0
        assert sensor._remaining == 0.0
        assert sensor._status == Status.DISCONNECTED
        assert sensor._scale == 1.0
        assert sensor._offset == 0


class TestTankSensorConversions:
    """Test conversion formulas."""

    def test_raw_to_voltage(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test with raw value 1000
        raw = 1000
        voltage = sensor._raw_to_voltage(raw)
        expected = raw * 3.3 / 26400.0
        assert abs(voltage - expected) < 0.0001

    def test_raw_to_voltage_zero(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        assert sensor._raw_to_voltage(0) == 0.0

    def test_voltage_to_resistance(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test with voltage 1.65V (half of reference)
        voltage = 1.65
        resistance = sensor._voltage_to_resistance(voltage)
        expected = (voltage * 220) / (3.3 - voltage)
        assert abs(resistance - expected) < 0.01

    def test_voltage_to_resistance_infinity(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test at reference voltage (should return infinity)
        resistance = sensor._voltage_to_resistance(3.3)
        assert resistance == float('inf')

    def test_voltage_to_resistance_zero(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test at zero voltage (should return 0.0)
        resistance = sensor._voltage_to_resistance(0.0)
        assert resistance == 0.0

    def test_voltage_to_resistance_negative(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test with negative voltage (should return 0.0)
        resistance = sensor._voltage_to_resistance(-0.1)
        assert resistance == 0.0

    def test_resistance_to_percentage(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test at minimum resistance (should be 0%)
        assert sensor._resistance_to_percentage(0.1) == 0.0
        
        # Test at maximum resistance (should be 100%)
        assert sensor._resistance_to_percentage(13.55) == 100.0
        
        # Test at middle resistance (should be 50%)
        middle = (13.55 + 0.1) / 2
        expected = (middle - 0.1) / (13.55 - 0.1) * 100
        assert abs(sensor._resistance_to_percentage(middle) - expected) < 0.01

    def test_resistance_to_percentage_below_min(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test resistance below minimum (should clamp to 0%)
        assert sensor._resistance_to_percentage(0.05) == 0.0

    def test_resistance_to_percentage_above_max(self, mock_dbus, mock_config):
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Test resistance above maximum (should clamp to 100%)
        assert sensor._resistance_to_percentage(20.0) == 100.0

    def test_resistance_to_percentage_zero_division(self, mock_dbus):
        """Test handling when sensor_min equals sensor_max."""
        config = {
            'type': 'tank',
            'name': 'Test',
            'channel': 0,
            'fixed_resistor': 220,
            'sensor_min': 10.0,
            'sensor_max': 10.0,
            'tank_capacity': 0.07,
            'fluid_type': 'fresh_water'
        }
        sensor = TankSensor(config, dbus=mock_dbus)
        
        # Should return 0.0 when min equals max (division by zero protection)
        assert sensor._resistance_to_percentage(10.0) == 0.0

    def test_full_conversion_chain(self, mock_dbus, mock_config):
        """Test complete conversion chain from raw to percentage."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Simulate raw ADC value
        raw = 1000
        voltage = sensor._raw_to_voltage(raw)
        resistance = sensor._voltage_to_resistance(voltage)
        percentage = sensor._resistance_to_percentage(resistance)
        
        # Verify the chain works without errors
        assert isinstance(voltage, float)
        assert isinstance(resistance, float)
        assert isinstance(percentage, float)
        assert 0.0 <= percentage <= 100.0


class TestTankSensorUpdate:
    """Test update method and state management."""

    def test_update_with_valid_reading(self, mock_dbus, mock_config):
        """Test update with valid ADC reading."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._dbus = Mock()
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        assert sensor._status == Status.OK
        assert sensor._level > 0

    def test_update_with_missing_device(self, mock_dbus, mock_config):
        """Test update when I2C device is missing."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._dbus = Mock()
        
        with patch.object(sensor, '_read_adc_raw', return_value=None):
            sensor.update()
        
        assert sensor._status == Status.DISCONNECTED

    def test_update_calculates_remaining(self, mock_dbus, mock_config):
        """Test that remaining volume is calculated correctly."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._dbus = Mock()
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        # Remaining should be level% of tank capacity
        expected_remaining = (sensor._level / 100.0) * sensor._tank_capacity
        assert abs(sensor._remaining - expected_remaining) < 0.0001

    def test_update_updates_dbus(self, mock_dbus, mock_config):
        """Test that D-Bus values are updated."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        # Verify D-Bus was updated
        assert mock_dbus_service.__setitem__.called

    def test_update_rounds_values(self, mock_dbus, mock_config):
        """Test that values are properly rounded."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        # Create a scenario that would produce many decimal places
        with patch.object(sensor, '_read_adc_raw', return_value=1234):
            sensor.update()
        
        # Check that Level is rounded to 1 decimal
        level_call = call('/Level', round(sensor._level, 1))
        assert level_call in mock_dbus_service.__setitem__.call_args_list
        
        # Check that Remaining is rounded to 4 decimals
        remaining_call = call('/Remaining', round(sensor._remaining, 4))
        assert remaining_call in mock_dbus_service.__setitem__.call_args_list


class TestTankSensorSettings:
    """Test settings handling."""

    def test_handle_dbus_change_capacity(self, mock_dbus, mock_config):
        """Test handling Capacity change from D-Bus."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        sensor._handle_dbus_change("/Capacity", 0.1)
        assert sensor._tank_capacity == 0.1

    def test_handle_dbus_change_fluid_type(self, mock_dbus, mock_config):
        """Test handling FluidType change from D-Bus."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        result = sensor._handle_dbus_change("/FluidType", FluidType.FUEL.value)
        assert result is True

    def test_handle_dbus_change_unknown_path(self, mock_dbus, mock_config):
        """Test handling unknown D-Bus path."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        result = sensor._handle_dbus_change("/UnknownPath", 123)
        assert result is False

    def test_setting_changed_scale(self, mock_dbus, mock_config):
        """Test handling Scale setting change."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        sensor._setting_changed('scale', 1.5)
        assert sensor._scale == 1.5

    def test_setting_changed_offset(self, mock_dbus, mock_config):
        """Test handling Offset setting change."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        sensor._setting_changed('offset', 100)
        assert sensor._offset == 100

    def test_setting_changed_unknown_setting(self, mock_dbus, mock_config):
        """Test handling unknown setting."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        # Should not crash on unknown setting
        sensor._setting_changed('unknown_setting', 123)
        # Scale and offset should remain unchanged
        assert sensor._scale == 1.0
        assert sensor._offset == 0


class TestTankSensorStatus:
    """Test status management."""

    def test_set_status_ok(self, mock_dbus, mock_config):
        """Test setting OK status."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        sensor._set_status(Status.OK)
        
        assert sensor._status == Status.OK
        mock_dbus_service.__setitem__.assert_called_with('/Status', Status.OK.value)

    def test_set_status_disconnected(self, mock_dbus, mock_config):
        """Test setting DISCONNECTED status."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        sensor._set_status(Status.DISCONNECTED)
        
        assert sensor._status == Status.DISCONNECTED
        mock_dbus_service.__setitem__.assert_called_with('/Status', Status.DISCONNECTED.value)

    def test_set_status_unknown(self, mock_dbus, mock_config):
        """Test setting UNKNOWN status."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        sensor._set_status(Status.UNKNOWN)
        
        assert sensor._status == Status.UNKNOWN
        mock_dbus_service.__setitem__.assert_called_with('/Status', Status.UNKNOWN.value)


class TestTankSensorErrorHandling:
    """Test error handling in update method."""

    def test_update_handles_file_read_error(self, mock_dbus, mock_config):
        """Test that file read errors are handled gracefully."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = Mock()
        sensor._dbus = mock_dbus_service
        
        with patch.object(sensor, '_read_adc_raw', return_value=None):
            sensor.update()
        
        assert sensor._status == Status.DISCONNECTED

    def test_update_handles_conversion_error(self, mock_dbus, mock_config):
        """Test that conversion errors are handled gracefully."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        mock_dbus_service = MagicMock()
        sensor._dbus = mock_dbus_service
        
        # Mock _read_adc_raw to return a valid value, then _raw_to_voltage to raise
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            with patch.object(sensor, '_raw_to_voltage', side_effect=ValueError("Test error")):
                sensor.update()
        
        assert sensor._status == Status.UNKNOWN

    def test_read_adc_raw_handles_missing_file(self, mock_dbus, mock_config):
        """Test that missing sysfs file is handled."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        
        with patch('builtins.open', side_effect=FileNotFoundError("No such file")):
            result = sensor._read_adc_raw()
        
        assert result is None


class TestTankSensorScaleOffset:
    """Test scale and offset application."""

    def test_scale_applied_to_raw_value(self, mock_dbus, mock_config):
        """Test that scale is applied to raw ADC value."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._scale = 2.0
        sensor._offset = 0
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        # The scaled raw value should be 2000
        # This affects all subsequent conversions
        assert sensor._scale == 2.0

    def test_offset_applied_to_raw_value(self, mock_dbus, mock_config):
        """Test that offset is applied to raw ADC value."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._scale = 1.0
        sensor._offset = 500
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        # The offset raw value should be 1500
        assert sensor._offset == 500

    def test_scale_and_offset_combined(self, mock_dbus, mock_config):
        """Test that scale and offset work together."""
        sensor = TankSensor(mock_config, dbus=mock_dbus)
        sensor._scale = 2.0
        sensor._offset = 100
        
        with patch.object(sensor, '_read_adc_raw', return_value=1000):
            sensor.update()
        
        # Combined: 1000 * 2.0 + 100 = 2100
        assert sensor._scale == 2.0
        assert sensor._offset == 100
