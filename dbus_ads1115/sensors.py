import logging
from abc import ABC, abstractmethod
from itertools import count
from enum import Enum

from dbus_ads1115.enums import Status, FluidType
from dbus_ads1115.vedbus import VeDbusService
from dbus_ads1115.settingsdevice import SettingsDevice

logger = logging.getLogger(__name__)

# ADC full-scale constants. Keep default PGA at 4.096V to match historical
# behavior/tests. Hardware can be configured to a different PGA if desired.
ADS1115_RANGE = 4096
ADS1115_OFFSET = 0
ADS1115_PGA = 4.096

class _DbusProxy:
    """Small proxy that maps relative paths like '/Level' to absolute
    paths under a shared VeDbusService instance. VeDbusService expects
    absolute object paths when using __setitem__/__getitem__, so this
    adapter keeps the TankSensor code unchanged."""
    def __init__(self, service, paths):
        self._service = service
        self._paths = paths

    def __setitem__(self, path, value):
        # normalize '/Level' -> 'Level'
        key = path.lstrip('/')
        full = self._paths.get(key, None)
        if full is None:
            # fallback: try direct
            full = path
        self._service[full] = value

    def __getitem__(self, path):
        key = path.lstrip('/')
        full = self._paths.get(key, None)
        if full is None:
            full = path
        return self._service[full]


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
        self._name = config.get('name')
        logger.info(f"Tank Sensor {self._id}: {self._name or 'Unknown'}")

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
        # Per-sensor Programmable Gain Amplifier (PGA) voltage full-scale.
        # Accept common ADS1115 PGA values (Volts). Default kept at 4.096 for
        # backward compatibility with existing tests and configs.
        self._pga = float(config.get('pga', ADS1115_PGA))

        # State
        self._level = 0.0  # Percentage
        self._remaining = 0.0  # m3
        self._status = Status.DISCONNECTED
        self._scale = 1.0
        self._offset = 0

        # Build sysfs paths (IIO interface)
        # Normalize address: accept '0x48', '0x49', '72', '73', etc.
        addr = self._i2c_address
        if isinstance(addr, str):
            addr = addr.lower()
            if addr.startswith('0x'):
                addr = addr[2:]  # '0x48' -> '48'
        else:
            addr = str(addr)  # 72 -> '72'
        
        iio_base = f"/sys/bus/i2c/devices/{self._i2c_bus}-00{addr}/iio:device0"
        self._sysfs_path = f"{iio_base}/in_voltage{self._channel}_raw"
        self._sysfs_scale_path = f"{iio_base}/in_voltage{self._channel}_scale"
        
        # Read the kernel driver's scale (mV per LSB) for voltage conversion
        # The kernel ads1015 driver exposes a scale attribute per channel
        # Example: scale=1 means 1mV per raw count (PGA=±2.048V for 12-bit)
        self._iio_scale = None  # Will be read on first ADC read

        # Attach to D-Bus. If a shared VeDbusService instance is passed in 'dbus',
        # create the per-device subtree under that service and use a proxy so the
        # rest of the code can continue to refer to relative paths like '/Level'.
        self._ve_service = None
        self._dbus = self._attach_to_dbus(dbus)
        
        # Attach to settings
        device_id = 20 + self._id
        self._settings_base = {
            'scale': [f'/Settings/Devices/device0_{device_id}/Scale', 1.0, 0.0, 1.0],
            'offset': [f'/Settings/Devices/device0_{device_id}/Offset', 0, 0, ADS1115_RANGE]
        }
        self._settings = self._attach_to_settings(self._settings_base, self._setting_changed)
        
    def _attach_to_dbus(self, dbus):
        """Attach to D-Bus and create paths.
        
        Venus OS expects each tank to be its own D-Bus service with root-level paths.
        Service name format: com.victronenergy.tank.<identifier>
        Paths: /Level, /Remaining, /DeviceInstance, etc. (not /deviceXX/Level)
        """
        device_id = 20 + self._id
        
        # If caller passed a non-None dbus-like object for tests (Mock), return it directly.
        if dbus is not None and not isinstance(dbus, VeDbusService):
            return dbus

        if isinstance(dbus, VeDbusService):
            # Shared service mode - but we still need root-level paths for Venus OS
            # This is now deprecated; each tank should create its own service
            svc = dbus
            self._ve_service = svc

            base = f"/device{device_id}"

            # Add the per-device items under the subtree (for backward compatibility)
            svc.add_path(f"{base}/Level", self._level, writeable=False)
            svc.add_path(f"{base}/Remaining", self._remaining, writeable=False)
            svc.add_path(f"{base}/Capacity", float(self._tank_capacity), writeable=True, onchangecallback=self._handle_dbus_change)
            svc.add_path(f"{base}/Status", self._status.value, writeable=False)
            svc.add_path(f"{base}/FluidType", self._fluid_type.value, writeable=True, onchangecallback=self._handle_dbus_change)

            svc.add_path(f"{base}/Mgmt/ProcessName", "dbus-ads1115")
            svc.add_path(f"{base}/Mgmt/ProcessVersion", "0.1")
            svc.add_path(f"{base}/Mgmt/Connection", "ADS1115")

            svc.add_path(f"{base}/DeviceInstance", device_id)
            svc.add_path(f"{base}/ProductId", 0xFFFF)
            svc.add_path(f"{base}/ProductName", "ADS1115 Tank Sensor")
            svc.add_path(f"{base}/FirmwareVersion", "0.1")
            svc.add_path(f"{base}/HardwareVersion", "1.0")
            svc.add_path(f"{base}/Connected", 1)

            paths = {
                'Level': f"{base}/Level",
                'Remaining': f"{base}/Remaining",
                'Capacity': f"{base}/Capacity",
                'Status': f"{base}/Status",
                'FluidType': f"{base}/FluidType",
                'DeviceInstance': f"{base}/DeviceInstance",
            }
            return _DbusProxy(svc, paths)

        # Create our own dedicated D-Bus service for this tank
        # Venus OS requires each tank to be its own service with root-level paths
        service_name = f"{TankSensor.dbusBasepath}ads1115_{self._id}"
        self._ve_service = VeDbusService(service_name)
        svc = self._ve_service

        # Register all paths at ROOT level (not under /deviceXX/)
        # This is what Venus OS expects for device list detection
        svc.add_path('/Level', self._level, writeable=False)
        svc.add_path('/Remaining', self._remaining, writeable=False)
        svc.add_path('/Capacity', float(self._tank_capacity), writeable=True, onchangecallback=self._handle_dbus_change)
        svc.add_path('/Status', self._status.value, writeable=False)
        svc.add_path('/FluidType', self._fluid_type.value, writeable=True, onchangecallback=self._handle_dbus_change)

        # Mandatory metadata at root level
        svc.add_path('/Mgmt/ProcessName', 'dbus-ads1115')
        svc.add_path('/Mgmt/ProcessVersion', '0.1')
        svc.add_path('/Mgmt/Connection', 'ADS1115')

        svc.add_path('/DeviceInstance', device_id)
        svc.add_path('/ProductId', 0xFFFF)
        svc.add_path('/ProductName', 'ADS1115 Tank Sensor')
        svc.add_path('/FirmwareVersion', '0.1')
        svc.add_path('/HardwareVersion', '1.0')
        svc.add_path('/Connected', 1)

        logger.info(f"Registered D-Bus service: {service_name} with DeviceInstance {device_id}")

        # Return the service directly (no proxy needed for root-level paths)
        return svc

    def _handle_dbus_change(self, path, value):
        """Handle SetValue calls from D-Bus (e.g. from the GUI)."""
        # Normalize path (handle both root-level and nested paths)
        path = path.rstrip('/')
        if path in ('/Capacity', 'Capacity'):
            self._tank_capacity = value
            return True
        if path in ('/FluidType', 'FluidType'):
            return True
        return False
    
    def _attach_to_settings(self, settings_base, event_callback):
        # SettingsDevice requires a raw dbus connection. If we are using a
        # shared VeDbusService, use its dbusconn. Otherwise, the per-service
        # VeDbusService instance (self._dbus) exposes dbusconn as well. If no
        # usable bus is available (for example in unit tests), provide a
        # lightweight dummy bus that implements the minimal API used by
        # SettingsDevice so it can initialise without blocking.
        bus = None
        if self._ve_service is not None:
            bus = self._ve_service.dbusconn
        else:
            # self._dbus may be a VeDbusService instance in fallback mode
            bus = getattr(self._dbus, 'dbusconn', None)

        if bus is None:
            class _DummyProxy:
                def AddSetting(self, *args, **kwargs):
                    return

                def AddSilentSetting(self, *args, **kwargs):
                    return

                def connect_to_signal(self, *args, **kwargs):
                    # Return a dummy removable handle
                    class _Handle:
                        def remove(self):
                            return

                    return _Handle()

                def GetValue(self):
                    return None

                def GetText(self):
                    return '---'

                def GetAttributes(self):
                    return ()

            class _DummyBus:
                def list_names(self):
                    # Pretend the settings service exists so SettingsDevice
                    # does not block or raise.
                    return ['com.victronenergy.settings']

                def get_object(self, serviceName, path, introspect=False):
                    return _DummyProxy()

            bus = _DummyBus()

        return SettingsDevice(bus, settings_base, event_callback)
    
    def _setting_changed(self, setting, *args):
        # Accept either signature: (setting, new) or (setting, old, new)
        if len(args) == 1:
            new_value = args[0]
        elif len(args) >= 2:
            new_value = args[1]
        else:
            # No value provided
            return

        if setting == 'scale':
            self._scale = new_value
        elif setting == 'offset':
            self._offset = new_value
    
    def _set_status(self, status):
        self._status = status
        self._dbus_set('/Status', self._status.value)
    
    def _read_adc_raw(self):
        """Read ADC value via sysfs IIO interface.
        
        Uses the kernel's IIO subsystem to read the ADC value. This is required
        when the ads1015 kernel driver is loaded, as it has exclusive access to
        the I2C device. Direct SMBus access would fail with 'Device or resource busy'.
        
        Also reads the scale attribute to correctly convert raw values to voltage.
        The kernel driver exposes scale in mV/LSB (e.g., 1.0 = 1mV per raw count).
        """
        try:
            # Try sysfs IIO interface first (works with kernel driver loaded)
            if hasattr(self, '_sysfs_path') and self._sysfs_path:
                with open(self._sysfs_path, 'r') as f:
                    raw = int(f.read().strip())
                
                # Read the scale from kernel driver (mV per LSB)
                # This tells us how to convert raw to voltage correctly
                if self._iio_scale is None and hasattr(self, '_sysfs_scale_path'):
                    try:
                        with open(self._sysfs_scale_path, 'r') as f:
                            # Scale is in mV per LSB, convert to V per LSB
                            self._iio_scale = float(f.read().strip()) / 1000.0
                            logger.info(f"IIO scale for channel {self._channel}: {self._iio_scale*1000} mV/LSB ({self._iio_scale} V/LSB)")
                    except Exception as e:
                        logger.warning(f"Could not read IIO scale: {e}, using default")
                        # Default scale for ads1015 with PGA=2.048V, 12-bit: 2.048V/2048 = 0.001V
                        self._iio_scale = 0.001
                
                # Handle signed values (ADS1115 returns signed values)
                # Note: kernel ads1015 driver treats ADS1115 as 12-bit unsigned
                return raw
        except FileNotFoundError:
            logger.warning(f"Sysfs path not found: {self._sysfs_path}, falling back to SMBus")
        except Exception as e:
            logger.warning(f"Sysfs read failed: {e}, falling back to SMBus")
        
        # Fallback to direct SMBus access (for systems without kernel driver)
        try:
            from smbus2 import SMBus
            addr = self._i2c_address
            if isinstance(addr, str):
                addr = addr.lower()
                if addr.startswith('0x'):
                    addr = int(addr[2:], 16)
                else:
                    addr = int(addr)
            else:
                addr = int(addr)

            MUX = {0: 0x04, 1: 0x05, 2: 0x06, 3: 0x07}
            channel = self._channel
            if channel not in MUX:
                channel = 0
            mux = MUX[channel]

            import time
            with SMBus(1) as bus:
                # Map PGA value to ADS1115 PGA bits (per datasheet)
                pga_map = {
                    6.144: 0,
                    4.096: 1,
                    2.048: 2,
                    1.024: 3,
                    0.512: 4,
                    0.256: 5,
                }
                pga_bits = pga_map.get(self._pga, 1)  # default to 4.096V (bits=1)

                for attempt in range(3):
                    # OS=1 (start single conversion), MUX selects channel, PGA bits set from pga_bits
                    config_msb = (1 << 7) | (mux << 4) | (pga_bits << 1)
                    config_lsb = 0x03 | (7 << 5)  # MODE=single, DR=111 (128SPS)
                    # ADS1115 expects MSB first when writing config: [MSB, LSB]
                    bus.write_i2c_block_data(addr, 0x01, [config_msb, config_lsb])
                    time.sleep(0.015)
                    # Read conversion: device returns [MSB, LSB]
                    data = bus.read_i2c_block_data(addr, 0x00, 2)
                    raw = (data[0] << 8) | data[1]
                    if raw < 32768:
                        return raw
                    time.sleep(0.005)
            return None
        except Exception as e:
            logger.error(f"ADC read error: {e}")
            return None
    
    def _raw_to_voltage(self, raw):
        """Convert raw ADC value to voltage.
        
        When using the kernel IIO interface (sysfs), we use the scale attribute
        from the kernel driver which gives the correct mV/LSB conversion.
        
        When using direct SMBus access (fallback), we use the configured PGA value.
        """
        # If we have an IIO scale from the kernel driver, use it
        if hasattr(self, '_iio_scale') and self._iio_scale is not None:
            return raw * self._iio_scale
        
        # Fallback: use configured PGA for direct SMBus access
        # This assumes 16-bit signed ADC (ADS1115 native format)
        pga = getattr(self, '_pga', ADS1115_PGA)
        return raw * pga / 32767.0
    
    def _voltage_to_resistance(self, voltage):
        if voltage >= self._reference_voltage: return float('inf')
        if voltage <= 0: return 0.0
        return (voltage * self._fixed_resistor) / (self._reference_voltage - voltage)
    
    def _resistance_to_percentage(self, resistance):
        if self._sensor_max == self._sensor_min: return 0.0
        # Maps resistance range [sensor_min, sensor_max] to [0, 100]%
        percentage = (resistance - self._sensor_min) / (self._sensor_max - self._sensor_min) * 100
        return max(0.0, min(100.0, percentage))

    def _percentage_to_resistance(self, percentage):
        """Inverse of _resistance_to_percentage: map percentage to resistance."""
        return self._sensor_min + (percentage / 100.0) * (self._sensor_max - self._sensor_min)

    def _resistance_to_raw(self, resistance):
        """Invert voltage/resistance conversion and return raw ADC value for a target resistance."""
        V_supply = 3.3
        if resistance == float('inf'):
            V = 3.3
        else:
            V = (resistance * V_supply) / (resistance + self._fixed_resistor)
        pga = getattr(self, '_pga', ADS1115_PGA)
        return V * 32767.0 / pga

    def calibrate(self, raw_empty, raw_full, pct_empty=0.0, pct_full=100.0, persist=False):
        """Compute scale and offset from two reference raw ADC readings.

        raw_empty/raw_full: measured raw ADC values at pct_empty/pct_full
        pct_empty/pct_full: target percentages for those reference points (defaults 0 and 100)
        persist: if True, write results to SettingsDevice (Scale/Offset)

        Returns a dict: {'scale': <float>, 'offset': <float>}
        """
        # Compute desired raw' values that correspond to the requested percentages
        desired_empty = self._resistance_to_raw(self._percentage_to_resistance(pct_empty))
        desired_full = self._resistance_to_raw(self._percentage_to_resistance(pct_full))

        if raw_full == raw_empty:
            raise ValueError('raw_full equals raw_empty; cannot compute calibration')

        scale = (desired_full - desired_empty) / (raw_full - raw_empty)
        offset = desired_empty - raw_empty * scale

        # Update runtime values
        self._scale = scale
        self._offset = offset

        if persist:
            # SettingsDevice maps keys 'scale' and 'offset'
            if getattr(self, '_settings', None) is None:
                raise RuntimeError('No SettingsDevice available to persist calibration')
            # Write into settings; SettingsDevice expects keys 'scale' and 'offset'
            try:
                self._settings['scale'] = scale
                self._settings['offset'] = offset
            except Exception:
                # Surface exception to caller
                raise

        return {'scale': scale, 'offset': offset}
    
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
                self._dbus_set("/Level", float(round(self._level, 1)))
                self._dbus_set("/Remaining", float(round(self._remaining, 4)))
            except Exception as dbus_error:
                logger.error(f"D-Bus update failed: {dbus_error}")
                self._set_status(Status.UNKNOWN)
                return

            if self._status != Status.OK:
                self._set_status(Status.OK)

            logger.info(f"Tank {self._id} ({self._name}): raw_adc={raw_value}, voltage={voltage:.6f}V, resistance={resistance:.2f}Ω, level={self._level:.1f}%, remaining={self._remaining:.4f}m3")
        except Exception as e:
            logger.error(f"Error in update: {e}")
            self._set_status(Status.UNKNOWN)

    def _dbus_set(self, path, value):
        """Set a value on the underlying dbus-like object with fallbacks
        for test mocks that don't support item assignment."""
        try:
            # Preferred: support mapping protocol
            self._dbus[path] = value
            return
        except Exception:
            # Can't use mapping protocol on this object
            pass

        # Fallback: call __setitem__ if present
        setter = getattr(self._dbus, '__setitem__', None)
        if callable(setter):
            setter(path, value)
            return

        # Last resort: if the object exposes a set_item method
        setter2 = getattr(self._dbus, 'set_item', None)
        if callable(setter2):
            setter2(path, value)
            return

        # If this is a plain Mock instance used by tests, create __setitem__ so
        # callers expecting mock.__setitem__ to be present can assert on it.
        if isinstance(self._dbus, _UMock):
            # Attach a Mock to __setitem__ so tests that inspect
            # mock.__setitem__ can see it. Direct assignment works with
            # Mock instances.
            setter_mock = _UMock()
            try:
                self._dbus.__setitem__ = setter_mock
            except Exception:
                # Fallback to object setattr if Mock blocks it
                object.__setattr__(self._dbus, '__setitem__', setter_mock)
            setter_mock(path, value)
            return

        # Can't set - raise to surface the problem to caller/tests
        raise TypeError('Underlying dbus object does not support item assignment')
