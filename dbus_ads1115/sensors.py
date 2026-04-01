import logging
from abc import ABC, abstractmethod
from itertools import count
from enum import Enum

from dbus_ads1115.enums import Status, FluidType
from dbus_ads1115.vedbus import VeDbusService
from dbus_ads1115.settingsdevice import SettingsDevice

logger = logging.getLogger(__name__)

ADS1115_RANGE = 4096
ADS1115_OFFSET = 0


class TankSensor:
    """A tank level sensor for resistive sensors."""

    dbusBasepath = "com.victronenergy.tank."
    _ids = count(0)

    # Fluid type mapping
    FLUID_TYPE_MAP = {
        'fresh_water': FluidType.FRESH_WATER,
        'waste_water': FluidType.WASTE_WATER,
        'fuel': FluidType.FUEL,
        'oil': FluidType.OIL,
        'black_water': FluidType.BLACK_WATER,
        'live_well': FluidType.LIVE_WELL
    }

    # Shared D-Bus connection for all sensors
    _shared_dbus = None
    
    def __init__(self, config, dbus=None):
        """Initialize TankSensor from configuration."""
        self._config = config
        self._id = next(self._ids)
        logger.info(f"Tank Sensor {self._id}: {config.get('name', 'Unknown')}")

        # Configuration
        self._channel = config['channel']
        self._fixed_resistor = config['fixed_resistor']
        self._sensor_min = config['sensor_min']
        self._sensor_max = config['sensor_max']
        self._tank_capacity = config['tank_capacity']
        self._fluid_type = self.FLUID_TYPE_MAP.get(config['fluid_type'], FluidType.FRESH_WATER)
        self._reference_voltage = config.get('reference_voltage', 3.3)
        self._i2c_bus = config.get('i2c_bus', 1)
        self._i2c_address = config.get('i2c_address', '0x48')

        # State
        self._level = 0.0  # Percentage
        self._remaining = 0.0  # m3
        self._status = Status.DISCONNECTED
        self._scale = 1.0
        self._offset = 0

        # Build sysfs path (IIO interface)
        self._sysfs_path = f"/sys/bus/i2c/devices/{self._i2c_bus}-00{self._i2c_address[2:]}/iio:device0/in_voltage{self._channel}_raw"

        # Attach to D-Bus
        self._dbus = self._attach_to_dbus(dbus)
        
        # Attach to settings
        device_id = 20 + self._id
        self._settings_base = {
            'scale': [f'/Settings/Devices/device0_{device_id}/Scale', 1.0, 0.0, 1.0],
            'offset': [f'/Settings/Devices/device0_{device_id}/Offset', 0, 0, ADS1115_RANGE]
        }
        self._settings = self._attach_to_settings(self._settings_base, self._setting_changed)
        
    def _attach_to_dbus(self, dbus):
        """Attach to D-Bus and create paths."""
        device_id = 20 + self._id
        service_name = f"{TankSensor.dbusBasepath}device0_{device_id}"

        # Create truly separate D-Bus connection for each sensor
        import dbus
        import time
        # Use BusConnection to get a unique connection instead of the singleton SystemBus
        bus = dbus.bus.BusConnection(dbus.bus.BUS_SYSTEM)

        try:
            _dbus = VeDbusService(service_name, bus=bus)
        except dbus.exceptions.NameExistsException:
            # Service name already exists, use temporary unique name for testing
            logger.warning(f"Service name {service_name} already in use, using temporary name")
            unique_name = f"{TankSensor.dbusBasepath}test_{device_id}_{int(time.time() % 1000)}"
            logger.info(f"Using temporary service name: {unique_name}")
            _dbus = VeDbusService(unique_name, bus=bus)

        _dbus.add_path("/Level", self._level, writeable=False)
        _dbus.add_path("/Remaining", self._remaining, writeable=False)
        # Capacity is in m3. 70L = 0.07m3. Set as writeable to allow GUI setup.
        _dbus.add_path("/Capacity", float(self._tank_capacity), writeable=True, onchangecallback=self._handle_dbus_change)
        _dbus.add_path("/Status", self._status.value, writeable=False)
        _dbus.add_path("/FluidType", self._fluid_type.value, writeable=True, onchangecallback=self._handle_dbus_change)

        _dbus.add_mandatory_paths(
            processname="dbus-ads1115",
            processversion="0.1",
            connection="ADS1115",
            deviceinstance=20 + self._id,
            productid=0x1000,
            productname="ADS1115 Tank Sensor",
            firmwareversion="0.1",
            hardwareversion="1.0",
            connected=1
        )
        return _dbus

    def _handle_dbus_change(self, path, value):
        """Handle SetValue calls from D-Bus (e.g. from the GUI)."""
        if path == "/Capacity":
            self._tank_capacity = value
            return True
        if path == "/FluidType":
            # You might want to update self._fluid_type here too
            return True
        return False
    
    def _attach_to_settings(self, settings_base, event_callback):
        return SettingsDevice(self._dbus.dbusconn, settings_base, event_callback)
    
    def _setting_changed(self, setting, old, new):
        if setting == 'scale':
            self._scale = new
        elif setting == 'offset':
            self._offset = new
    
    def _set_status(self, status):
        self._status = status
        self._dbus["/Status"] = self._status.value
    
    def _read_adc_raw(self):
        try:
            with open(self._sysfs_path, 'r') as f:
                return int(f.read().strip())
        except:
            return None
    
    def _raw_to_voltage(self, raw):
        # Adjusted divisor as requested: 26400.0
        return raw * self._reference_voltage / 26400.0
    
    def _voltage_to_resistance(self, voltage):
        if voltage >= self._reference_voltage: return float('inf')
        if voltage <= 0: return 0.0
        return (voltage * self._fixed_resistor) / (self._reference_voltage - voltage)
    
    def _resistance_to_percentage(self, resistance):
        if self._sensor_max == self._sensor_min: return 0.0
        # Maps resistance range [sensor_min, sensor_max] to [0, 100]%
        percentage = (resistance - self._sensor_min) / (self._sensor_max - self._sensor_min) * 100
        return max(0.0, min(100.0, percentage))
    
    def update(self):
        raw_value = self._read_adc_raw()
        if raw_value is None:
            self._set_status(Status.DISCONNECTED)
            return
        
        try:
            raw_value = raw_value * self._scale + self._offset
            voltage = self._raw_to_voltage(raw_value)
            resistance = self._voltage_to_resistance(voltage)
            self._level = self._resistance_to_percentage(resistance)
            
            # Volume in m3 (match Capacity units)
            self._remaining = (self._level / 100.0) * self._tank_capacity

            try:
                self._dbus["/Level"] = float(round(self._level, 1))
                self._dbus["/Remaining"] = float(round(self._remaining, 4))
            except Exception as dbus_error:
                logger.error(f"D-Bus update failed: {dbus_error}")
                self._set_status(Status.UNKNOWN)
                return

            if self._status != Status.OK:
                self._set_status(Status.OK)

            logger.debug(f"Tank {self._id}: Raw={raw_value}, R={resistance:.2f}Ω, Level={self._level:.1f}%")
        except Exception as e:
            logger.error(f"Error in update: {e}")
            self._set_status(Status.UNKNOWN)
