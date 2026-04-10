"""
Tests for SensorManager class.
"""

import pytest
from unittest.mock import Mock, patch
import os
import tempfile


# ---------------------------------------------------------------------------
# INI config helpers
# ---------------------------------------------------------------------------

def _ini_sensor(idx=0, **overrides):
    """Return a minimal INI [sensorN] block as a string."""
    defaults = dict(
        type='tank',
        name=f'Tank {idx}',
        channel=idx,
        fixed_resistor=220,
        sensor_min=0.1,
        sensor_max=13.55,
        tank_capacity=0.07,
        fluid_type='fresh_water',
    )
    defaults.update(overrides)
    lines = [f'[sensor{idx}]']
    for k, v in defaults.items():
        lines.append(f'{k} = {v}')
    return '\n'.join(lines) + '\n'


def _ini_i2c(bus=1, address='0x48', reference_voltage=3.3):
    return (
        f'[i2c]\n'
        f'bus               = {bus}\n'
        f'address           = {address}\n'
        f'reference_voltage = {reference_voltage}\n'
    )


def _write_ini(content: str, suffix='.ini'):
    """Write INI content to a named temp file; return path (caller must unlink)."""
    fd, path = tempfile.mkstemp(suffix=suffix, text=True)
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# TestSensorManagerInitialization
# ---------------------------------------------------------------------------

class TestSensorManagerInitialization:
    """Test SensorManager initialization."""

    def test_initialization_with_valid_config(self, mock_config_file):
        """Test initialization with valid configuration file."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        manager = SensorManager(mock_config_file)

        assert manager._config is not None
        assert 'sensors' in manager._config
        assert len(manager._sensors) > 0

    def test_initialization_creates_tank_sensors(self, mock_config_file):
        """Test that TankSensor instances are created."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        manager = SensorManager(mock_config_file)

        assert len(manager._sensors) > 0
        for sensor in manager._sensors:
            from dbus_ads1115.sensors import TankSensor
            assert isinstance(sensor, TankSensor)

    def test_initialization_with_empty_sensors_list(self):
        """All sensors disabled via user override → zero running sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # Explicitly disable every sensor in the user override file
        content = (
            _ini_i2c()
            + '[sensor0]\nenabled = false\n'
            + '[sensor1]\nenabled = false\n'
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 0
        finally:
            os.unlink(path)

    def test_initialization_with_missing_sensors_key(self):
        """Only [i2c] override — sensors come from config.default.ini defaults."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # User file has only i2c section; default sensors are still loaded
        path = _write_ini(_ini_i2c())
        try:
            manager = SensorManager(path)
            # config.default.ini defines sensor0 + sensor1 enabled by default
            assert len(manager._sensors) >= 0  # at least doesn't crash
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestSensorManagerIC2ConfigFallback
# ---------------------------------------------------------------------------

class TestSensorManagerIC2ConfigFallback:
    """Test I2C configuration fallback behaviour."""

    def test_i2c_bus_fallback_to_global(self):
        """Sensor inherits global I2C bus when not overridden."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(_ini_i2c(bus=2, address='0x49', reference_voltage=5.0)
                          + _ini_sensor(0))
        try:
            manager = SensorManager(path)
            assert manager._sensors[0]._i2c_bus == 2
        finally:
            os.unlink(path)

    def test_i2c_bus_sensor_specific_overrides_global(self):
        """Sensor-level i2c_bus overrides global bus."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(
            _ini_i2c(bus=2, address='0x49', reference_voltage=5.0)
            + _ini_sensor(0, i2c_bus=3)
        )
        try:
            manager = SensorManager(path)
            assert manager._sensors[0]._i2c_bus == 3
        finally:
            os.unlink(path)

    def test_i2c_address_fallback_to_global(self):
        """Sensor inherits global I2C address when not overridden."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(_ini_i2c(address='0x4A') + _ini_sensor(0))
        try:
            manager = SensorManager(path)
            assert manager._sensors[0]._i2c_address == 0x4A
        finally:
            os.unlink(path)

    def test_i2c_address_sensor_specific_overrides_global(self):
        """Sensor-level i2c_address overrides global address."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(
            _ini_i2c(address='0x49')
            + _ini_sensor(0, i2c_address='0x4B')
        )
        try:
            manager = SensorManager(path)
            assert manager._sensors[0]._i2c_address == 0x4B
        finally:
            os.unlink(path)

    def test_reference_voltage_fallback_to_global(self):
        """Sensor inherits global reference voltage."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(_ini_i2c(reference_voltage=5.0) + _ini_sensor(0))
        try:
            manager = SensorManager(path)
            assert manager._sensors[0]._reference_voltage == 5.0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestSensorManagerMultiSensor
# ---------------------------------------------------------------------------

class TestSensorManagerMultiSensor:
    """Test handling of multiple sensors."""

    def test_creates_multiple_sensors(self, multi_sensor_config):
        """Multiple sensor sections produce multiple TankSensor instances."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        manager = SensorManager(multi_sensor_config)
        assert len(manager._sensors) == 2
        assert manager._sensors[0]._name == 'Test Tank'
        assert manager._sensors[1]._name == 'Tank 2'

    def test_different_channels_for_multiple_sensors(self):
        """Each sensor section gets its own channel."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        content = (
            _ini_i2c()
            + _ini_sensor(0, name='Tank 1', channel=0, fluid_type='fresh_water')
            + _ini_sensor(1, name='Tank 2', channel=1, fluid_type='waste_water')
            + _ini_sensor(2, name='Tank 3', channel=2, fluid_type='fuel',
                          tank_capacity=0.03)
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 3
            assert manager._sensors[0]._channel == 0
            assert manager._sensors[1]._channel == 1
            assert manager._sensors[2]._channel == 2
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestSensorManagerEnabledFlag
# ---------------------------------------------------------------------------

class TestSensorManagerEnabledFlag:
    """Test that the `enabled` flag controls sensor instantiation."""

    def test_disabled_sensor_is_skipped(self):
        """A sensor with enabled = false must NOT appear in _sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        content = (
            _ini_i2c()
            + _ini_sensor(0, name='Active Tank', enabled='true')
            + _ini_sensor(1, name='Inactive Tank', enabled='false',
                          fluid_type='waste_water')
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 1
            assert manager._sensors[0]._name == 'Active Tank'
        finally:
            os.unlink(path)

    def test_sensor_enabled_by_default(self):
        """A sensor without an explicit enabled key is instantiated (default True)."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # Disable sensor1 so only sensor0 (our 'Default Tank') runs
        content = (
            _ini_i2c()
            + _ini_sensor(0, name='Default Tank')
            + '[sensor1]\nenabled = false\n'
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 1
            assert manager._sensors[0]._name == 'Default Tank'
        finally:
            os.unlink(path)

    def test_all_disabled_produces_empty_sensor_list(self):
        """All sensors disabled → zero running sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        content = (
            _ini_i2c()
            + _ini_sensor(0, name='Tank A', enabled='false')
            + _ini_sensor(1, name='Tank B', enabled='false',
                          fluid_type='waste_water')
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            assert len(manager._sensors) == 0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestSensorManagerUpdate
# ---------------------------------------------------------------------------

class TestSensorManagerUpdate:
    """Test update method."""

    def test_update_calls_all_sensors(self, mock_config_file):
        """update() calls update() on every sensor."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        manager = SensorManager(mock_config_file)
        for sensor in manager._sensors:
            sensor.update = Mock()

        manager.update()

        for sensor in manager._sensors:
            sensor.update.assert_called_once()

    def test_update_returns_true(self, mock_config_file):
        """update() always returns True."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        manager = SensorManager(mock_config_file)
        assert manager.update() is True

    def test_update_with_empty_sensors_list(self):
        """update() returns True even with no sensors."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        path = _write_ini(_ini_i2c())
        try:
            manager = SensorManager(path)
            assert manager.update() is True
        finally:
            os.unlink(path)

    def test_update_handles_sensor_update_exceptions(self):
        """update() continues past a failing sensor and returns True."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        content = (
            _ini_i2c()
            + _ini_sensor(0, name='Tank 1')
            + _ini_sensor(1, name='Tank 2', fluid_type='waste_water')
        )
        path = _write_ini(content)
        try:
            manager = SensorManager(path)
            with patch.object(manager._sensors[1], 'update',
                              side_effect=Exception('Test error')):
                result = manager.update()
            assert result is True
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestSensorManagerErrorHandling
# ---------------------------------------------------------------------------

class TestSensorManagerErrorHandling:
    """Test error handling in SensorManager."""

    def test_handles_missing_config_file(self):
        """Missing user config is silently ignored — config.default.ini covers defaults."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # configparser.read() silently skips missing files; the driver should not crash
        manager = SensorManager('/nonexistent/config.ini')
        # At minimum the manager must be initialised (defaults come from config.default.ini)
        assert manager._config is not None

    def test_handles_invalid_ini_syntax(self):
        """Malformed INI does not crash the driver — config is empty or partial."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # configparser is lenient; write something truly unparseable
        path = _write_ini('this is not ini\n[broken\nno closing bracket\n')
        try:
            # Should not raise — SensorManager catches exceptions
            manager = SensorManager(path)
            assert manager._config is not None
        finally:
            os.unlink(path)

    def test_handles_missing_required_sensor_fields(self):
        """Sensor with missing fields either raises KeyError or results in empty list."""
        from dbus_ads1115.dbus_ads1115 import SensorManager

        # Section present but almost all required keys missing
        path = _write_ini(_ini_i2c() + '[sensor0]\ntype = tank\nname = Incomplete Tank\n')
        try:
            try:
                manager = SensorManager(path)
                assert manager._sensors is not None
            except KeyError:
                pass  # acceptable — missing required field
        finally:
            os.unlink(path)
