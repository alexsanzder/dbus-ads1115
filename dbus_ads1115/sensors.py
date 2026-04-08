import logging
from abc import ABC, abstractmethod
from itertools import count
from enum import Enum
import time

from dbus_ads1115.enums import Status, FluidType
from dbus_ads1115.vedbus import VeDbusService
from dbus_ads1115.settingsdevice import SettingsDevice

# Import dbus for creating separate connections per sensor
try:
    import dbus as _dbus_module
except ImportError:
    _dbus_module = None

# Package version – used in mandatory D-Bus metadata paths so that VRM Portal
# and the Venus OS GUI display the correct firmware string.
try:
    from dbus_ads1115 import __version__ as _PACKAGE_VERSION
except ImportError:
    _PACKAGE_VERSION = '0.0.0'  # Safety fallback – should never be reached in a proper install

logger = logging.getLogger(__name__)

# ADC full-scale constants. Keep default PGA at 4.096V to match historical
# behavior/tests. Hardware can be configured to a different PGA if desired.
ADS1115_RANGE = 4096
ADS1115_OFFSET = 0
ADS1115_PGA = 4.096

# Volume unit conversion factors → m³.
# Venus OS always stores /Capacity and /Remaining in m³ on D-Bus.
# The display unit (liters, gallons…) is a system-wide setting on the
# Cerbo GX / Venus OS at /Settings/System/VolumeUnit:
#   0 = m³  |  1 = Liters  |  2 = US gallons  |  3 = Imperial gallons
_VOLUME_TO_M3 = {
    'cubic_meters':    1.0,
    'm3':              1.0,
    'liters':          1e-3,
    'litres':          1e-3,
    'l':               1e-3,
    'gallons_us':      0.00378541,
    'us_gallons':      0.00378541,
    'gallons_imp':     0.00454609,
    'gallons_imperial':0.00454609,
    'imp_gallons':     0.00454609,
}

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
    """A tank level sensor for resistive sensors.

    Supports Venus OS level-based alarms through /Alarms/Low/State and
    /Alarms/High/State paths. These are monitored by venus-platform which
    creates notifications when alarm states change.

    Sensor fault conditions (disconnection, short circuit) also trigger
    notifications by setting /Alarms/Low/State to alarm state.
    """

    dbusBasepath = "com.victronenergy.tank."
    _ids = count(0)
    _used_service_names = set()  # Track used service names to avoid conflicts

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
        self._product_name = config.get('product_name', 'ADS1115 Tank Sensor')

        # ProductId: numeric Victron product identifier shown in VRM Portal.
        # Accepts an integer (0xA522) or a hex string ('0xA522') in config.
        # Defaults to 0xFFFF (generic / unknown) when not specified.
        _pid = config.get('product_id', 0xFFFF)
        if isinstance(_pid, str):
            _pid = _pid.strip()
            self._product_id = int(_pid, 16) if _pid.lower().startswith('0x') else int(_pid)
        else:
            self._product_id = int(_pid)

        logger.info(f"Tank Sensor {self._id}: {self._name or 'Unknown'}")

        # Configuration
        self._channel = config['channel']
        self._fixed_resistor = config['fixed_resistor']
        self._sensor_min = config['sensor_min']
        self._sensor_max = config['sensor_max']

        # Tank capacity — accept any common unit via the optional volume_unit key.
        # Internally everything is stored and published to D-Bus in m³.
        # Venus OS display unit is system-wide (/Settings/System/VolumeUnit on the GX).
        _raw_capacity = float(config['tank_capacity'])
        _vol_unit = str(config.get('volume_unit', 'cubic_meters')).lower().strip()
        _factor = _VOLUME_TO_M3.get(_vol_unit, None)
        if _factor is None:
            logger.warning(
                f"Tank '{self._name}': unknown volume_unit '{_vol_unit}', "
                f"assuming cubic_meters"
            )
            _factor = 1.0
            _vol_unit = 'cubic_meters'
        self._tank_capacity = _raw_capacity * _factor  # always m³ from here on
        self._volume_unit = _vol_unit
        logger.info(
            f"Tank '{self._name}': capacity {_raw_capacity} {_vol_unit} "
            f"= {self._tank_capacity:.6f} m³"
        )
        self._fluid_type = self.FLUID_TYPE_MAP.get(config['fluid_type'], FluidType.FRESH_WATER)
        self._reference_voltage = config.get('reference_voltage', 3.3)
        self._i2c_bus = config.get('i2c_bus', 1)
        self._i2c_address = config.get('i2c_address', '0x48')
        # Per-sensor Programmable Gain Amplifier (PGA) voltage full-scale.
        # Accept common ADS1115 PGA values (Volts). Default kept at 4.096 for
        # backward compatibility with existing tests and configs.
        self._pga = float(config.get('pga', ADS1115_PGA))

        # Channel mapping for ADS1115
        # Some ADS1115 modules or kernel drivers have inverted channel mapping.
        # This maps the logical channel (0, 1, 2, 3) to the physical IIO channel.
        # Default is identity mapping (0→0, 1→1, 2→2, 3→3).
        # Set i2c.channel_map in config if your module has different wiring.
        channel_map = config.get('channel_map', [0, 1, 2, 3])

        # Handle case where channel_map might be a string (if YAML not parsed correctly)
        # This can happen on Venus OS which uses a minimal YAML parser
        if isinstance(channel_map, str):
            try:
                import ast
                channel_map = ast.literal_eval(channel_map)
            except Exception:
                logger.warning("Could not parse channel_map string, using default [0, 1, 2, 3]")
                channel_map = [0, 1, 2, 3]

        if self._channel < len(channel_map):
            self._iio_channel = channel_map[self._channel]
        else:
            self._iio_channel = self._channel

        # State
        self._level = 0.0  # Percentage
        self._remaining = 0.0  # m3
        self._status = Status.DISCONNECTED
        self._scale = 1.0
        self._offset = 0

        # Startup settling period - don't trigger alarms until readings are stable
        # This prevents false alerts during boot when sensors take time to initialize
        self._startup_readings_count = 0
        self._startup_settling_readings = 5  # Number of readings before enabling alarms

        # Level-based alarm state (Venus OS compatible)
        # These are monitored by venus-platform for notifications
        # Read from config if provided, otherwise use defaults
        alarms_config = config.get('alarms', {})
        
        # Low level alarm configuration
        low_config = alarms_config.get('low', {})
        self._low_alarm_enabled = 1 if low_config.get('enable', False) else 0
        self._low_alarm_active = low_config.get('active', 10)      # Level % to trigger alarm
        self._low_alarm_restore = low_config.get('restore', 15)   # Level % to clear alarm
        self._low_alarm_delay = low_config.get('delay', 30)       # Delay in seconds before triggering
        self._low_alarm_state = 0        # Current state: 0=Ok, 1=Warning, 2=Alarm
        self._low_alarm_timer = None     # Timer for delay

        # High level alarm configuration
        high_config = alarms_config.get('high', {})
        self._high_alarm_enabled = 1 if high_config.get('enable', False) else 0
        self._high_alarm_active = high_config.get('active', 90)     # Level % to trigger alarm
        self._high_alarm_restore = high_config.get('restore', 80)  # Level % to clear alarm
        self._high_alarm_delay = high_config.get('delay', 5)       # Delay in seconds before triggering
        self._high_alarm_state = 0       # Current state: 0=Ok, 1=Warning, 2=Alarm
        self._high_alarm_timer = None    # Timer for delay

        # Track recent resistance readings for stability detection
        # A floating/disconnected sensor will have highly unstable readings
        self._resistance_history = []
        self._history_size = 5  # Number of readings to track
        self._stability_threshold = 0.01  # Max allowed relative std dev (1%)

        # Build sysfs paths (IIO interface)
        # Uses the mapped IIO channel, not the logical channel
        # Normalize address: accept '0x48', '0x49', '72', '73', etc.
        addr = self._i2c_address
        if isinstance(addr, str):
            addr = addr.lower()
            if addr.startswith('0x'):
                addr = addr[2:]  # '0x48' -> '48'
        else:
            addr = str(addr)  # 72 -> '72'

        iio_base = f"/sys/bus/i2c/devices/{self._i2c_bus}-00{addr}/iio:device0"
        self._sysfs_path = f"{iio_base}/in_voltage{self._iio_channel}_raw"
        self._sysfs_scale_path = f"{iio_base}/in_voltage{self._iio_channel}_scale"

        logger.info(f"Tank '{self._name}': logical channel {self._channel} -> IIO channel {self._iio_channel} -> sysfs path {self._sysfs_path}")

        # Read the kernel driver's scale (mV per LSB) for voltage conversion
        # The kernel ads1015 driver exposes a scale attribute per channel
        # Example: scale=1 means 1mV per raw count (PGA=±2.048V for 12-bit)
        self._iio_scale = None  # Will be read on first ADC read

        # Create a stable device identifier from tank name (not channel!)
        # This allows moving sensors between channels without losing settings/identity
        # Sanitize name: lowercase, replace spaces with underscores, remove special chars
        if self._name:
            device_identifier = ''.join(
                c if c.isalnum() or c == '_' else '_' 
                for c in self._name.lower().replace(' ', '_')
            ).strip('_')
            # Remove consecutive underscores
            while '__' in device_identifier:
                device_identifier = device_identifier.replace('__', '_')
        else:
            device_identifier = f'tank_{self._id}'
        
        self._device_identifier = device_identifier
        logger.info(f"Tank Sensor {self._id}: '{self._name}' -> device identifier '{device_identifier}'")

        # Default DeviceInstance (can be overridden by settings)
        # Use channel number for DeviceInstance (same as old code)
        self._device_instance = 20 + self._channel

        # Attach to settings BEFORE creating D-Bus service
        # This allows reading DeviceInstance from settings
        self._ve_service = None
        self._settings_dbus_connection = self._create_dbus_connection()
        
        # Attach to settings using Venus OS standard paths
        # Path format: /Settings/Devices/<device_identifier>/<setting>
        # This allows Venus OS GUI to discover and configure the tank
        self._settings_base = {
            # Device identification (required for VRM and GUI discovery)
            'instance': [f'/Settings/Devices/{device_identifier}/ClassAndVrmInstance', 
                        f'tank:{self._device_instance}', '', ''],
            'device_instance': [f'/Settings/Devices/{device_identifier}/DeviceInstance', 
                               self._device_instance, 0, 100],
            # Tank configuration
            'capacity': [f'/Settings/Devices/{device_identifier}/Capacity', 
                        float(self._tank_capacity), 0.0, 100000.0],
            'fluid_type': [f'/Settings/Devices/{device_identifier}/FluidType', 
                          self._fluid_type.value, 0, 11],
            'custom_name': [f'/Settings/Devices/{device_identifier}/CustomName', 
                           self._name or '', '', ''],
            # Sensor calibration (voltage-based)
            'raw_value_empty': [f'/Settings/Devices/{device_identifier}/RawValueEmpty', 
                               0.0, 0.0, 5.0],
            'raw_value_full': [f'/Settings/Devices/{device_identifier}/RawValueFull', 
                              3.3, 0.0, 5.0],
            # Legacy calibration (resistance-based)
            'scale': [f'/Settings/Devices/{device_identifier}/Scale', 1.0, 0.0, 10.0],
            'offset': [f'/Settings/Devices/{device_identifier}/Offset', 0, 0, ADS1115_RANGE],
        }
        self._settings = self._attach_to_settings(self._settings_base, self._setting_changed)
        
        # Read DeviceInstance from settings (may have been changed by user in GUI)
        try:
            stored_instance = self._settings.get('device_instance', self._device_instance)
            if stored_instance != self._device_instance:
                logger.info(f"Tank '{self._name}': Using DeviceInstance {stored_instance} from settings (was {self._device_instance})")
                self._device_instance = stored_instance
        except Exception as e:
            logger.warning(f"Could not read DeviceInstance from settings: {e}, using default {self._device_instance}")

        # Now create D-Bus service with correct DeviceInstance
        self._dbus = self._attach_to_dbus(dbus)

    def _create_dbus_connection(self):
        """Create a private D-Bus connection for settings access.
        
        This is needed before creating the D-Bus service so we can read
        settings (like DeviceInstance) from the com.victronenergy.settings service.
        """
        if _dbus_module is None:
            return None
        
        try:
            import os
            bus_address = os.environ.get(
                "DBUS_SYSTEM_BUS_ADDRESS",
                "unix:path=/var/run/dbus/system_bus_socket"
            )
            return _dbus_module.bus.BusConnection(bus_address)
        except Exception as e:
            logger.warning(f"Could not create private D-Bus connection for settings: {e}")
            return None

    def _attach_to_dbus(self, dbus):
        """Attach to D-Bus and create paths.

        Venus OS expects each tank to be its own D-Bus service with root-level paths.
        Service name format: com.victronenergy.tank.<identifier>
        Paths: /Level, /Remaining, /DeviceInstance, etc. (not under /deviceXX/Level)

        IMPORTANT: Each tank sensor needs its own private D-Bus connection because
        object paths are registered per-connection, not per-service-name. If we share
        the same connection, we can't have multiple services with the same paths (/Level, etc.).
        """
        # Use DeviceInstance from settings (or default from config position)
        device_id = self._device_instance

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

            # Level-based alarm paths (Venus OS notification system)
            svc.add_path(f"{base}/Alarms/Low/Enable", self._low_alarm_enabled, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/Low/Active", self._low_alarm_active, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/Low/Restore", self._low_alarm_restore, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/Low/Delay", self._low_alarm_delay, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/Low/State", self._low_alarm_state, writeable=False)

            svc.add_path(f"{base}/Alarms/High/Enable", self._high_alarm_enabled, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/High/Active", self._high_alarm_active, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/High/Restore", self._high_alarm_restore, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/High/Delay", self._high_alarm_delay, writeable=True, onchangecallback=self._handle_alarm_setting)
            svc.add_path(f"{base}/Alarms/High/State", self._high_alarm_state, writeable=False)

            # Legacy /Alarm path (kept for compatibility, but not monitored by venus-platform)
            self._alarm = 0
            svc.add_path(f"{base}/Alarm", self._alarm, writeable=False)

            svc.add_path(f"{base}/Mgmt/ProcessName", "dbus-ads1115")
            svc.add_path(f"{base}/Mgmt/ProcessVersion", _PACKAGE_VERSION)
            svc.add_path(f"{base}/Mgmt/Connection", "ADS1115")

            svc.add_path(f"{base}/DeviceInstance", device_id)
            svc.add_path(f"{base}/ProductId", self._product_id)
            svc.add_path(f"{base}/ProductName", self._product_name)
            svc.add_path(f"{base}/FirmwareVersion", _PACKAGE_VERSION)
            svc.add_path(f"{base}/HardwareVersion", "1.0")
            svc.add_path(f"{base}/Connected", 1)
            svc.add_path(f"{base}/CustomName", self._name or '', writeable=True,
                         onchangecallback=self._handle_dbus_change)

            paths = {
                'Level': f"{base}/Level",
                'Remaining': f"{base}/Remaining",
                'Capacity': f"{base}/Capacity",
                'Status': f"{base}/Status",
                'FluidType': f"{base}/FluidType",
                'DeviceInstance': f"{base}/DeviceInstance",
                'Alarm': f"{base}/Alarm",
                'Alarms/Low/State': f"{base}/Alarms/Low/State",
                'Alarms/High/State': f"{base}/Alarms/High/State",
            }
            return _DbusProxy(svc, paths)

        # Create our own dedicated D-Bus service for this tank
        # Venus OS requires each tank to be its own service with root-level paths
        # Use device_identifier for service name (stable, not tied to channel)
        base_service_name = f"{TankSensor.dbusBasepath}{self._device_identifier}"
        service_name = base_service_name

        # If this service name is already used by another sensor in this process,
        # append a unique suffix (shouldn't happen with channel-based names)
        if service_name in TankSensor._used_service_names:
            service_name = f"{TankSensor.dbusBasepath}ads1115_{self._id}"

        TankSensor._used_service_names.add(service_name)

        # Create a PRIVATE D-Bus connection for this sensor
        # This is critical: each sensor needs its own connection because object paths
        # are registered per-connection. Without this, multiple sensors can't have /Level
        # on the same shared connection even if they have different service names.
        private_bus = None
        if _dbus_module is not None:
            try:
                # Get the system bus address and create a truly private connection
                # BusConnection(BUS_SYSTEM) returns shared bus, so we need to use the address
                # Note: get_bus_address() may not exist on all dbus implementations (e.g., Venus OS)
                # Use environment variable as fallback
                import os
                bus_address = os.environ.get(
                    "DBUS_SYSTEM_BUS_ADDRESS",
                    "unix:path=/var/run/dbus/system_bus_socket"
                )
                private_bus = _dbus_module.bus.BusConnection(bus_address)
                logger.info(f"Created private D-Bus connection for {service_name}")
            except Exception as e:
                logger.warning(f"Could not create private D-Bus connection: {e}, using shared connection")
                private_bus = None

        self._ve_service = VeDbusService(service_name, bus=private_bus)
        svc = self._ve_service

        # Register all paths at ROOT level (not under /deviceXX/)
        # This is what Venus OS expects for device list detection
        svc.add_path('/Level', self._level, writeable=False)
        svc.add_path('/Remaining', self._remaining, writeable=False)
        svc.add_path('/Capacity', float(self._tank_capacity), writeable=True, onchangecallback=self._handle_dbus_change)
        svc.add_path('/Status', self._status.value, writeable=False)
        svc.add_path('/FluidType', self._fluid_type.value, writeable=True, onchangecallback=self._handle_dbus_change)

        # Level-based alarm paths (Venus OS notification system)
        # These paths are monitored by venus-platform to create notifications
        # when alarm states change from 0 (Ok) to 2 (Alarm)
        svc.add_path('/Alarms/Low/Enable', self._low_alarm_enabled, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/Low/Active', self._low_alarm_active, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/Low/Restore', self._low_alarm_restore, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/Low/Delay', self._low_alarm_delay, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/Low/State', self._low_alarm_state, writeable=False)

        svc.add_path('/Alarms/High/Enable', self._high_alarm_enabled, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/High/Active', self._high_alarm_active, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/High/Restore', self._high_alarm_restore, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/High/Delay', self._high_alarm_delay, writeable=True, onchangecallback=self._handle_alarm_setting)
        svc.add_path('/Alarms/High/State', self._high_alarm_state, writeable=False)

        # Legacy /Alarm path (kept for compatibility, but not monitored by venus-platform)
        # This was used for sensor fault alarms but Venus OS doesn't monitor it for tanks
        self._alarm = 0
        svc.add_path('/Alarm', self._alarm, writeable=False)

        # /CustomName: user-defined display name shown in the Venus OS GUI and VRM Portal.
        # Setting this overrides the auto-generated label for the device.
        svc.add_path('/CustomName', self._name or '', writeable=True,
                     onchangecallback=self._handle_dbus_change)

        # Mandatory metadata – use add_mandatory_paths() helper so we never
        # accidentally omit a required path.  Real version strings ensure VRM
        # Portal shows the correct firmware rather than '0.1'.
        svc.add_mandatory_paths(
            processname='dbus-ads1115',
            processversion=_PACKAGE_VERSION,
            connection='ADS1115 I2C',
            deviceinstance=device_id,
            productid=self._product_id,
            productname=self._product_name,
            firmwareversion=_PACKAGE_VERSION,
            hardwareversion='1.0',
            connected=1,
        )

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
        if path in ('/CustomName', 'CustomName'):
            # Update internal name; no secondary D-Bus write needed because the
            # caller already owns the value on the bus.
            self._name = str(value) if value is not None else ''
            logger.info(f"Tank {self._id}: CustomName changed to '{self._name}' via D-Bus")
            return True
        return False

    def _handle_alarm_setting(self, path, value):
        """Handle changes to alarm settings from the GUI."""
        path = path.rstrip('/')

        # Low alarm settings
        if path == '/Alarms/Low/Enable':
            self._low_alarm_enabled = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/Low/Active':
            self._low_alarm_active = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/Low/Restore':
            self._low_alarm_restore = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/Low/Delay':
            self._low_alarm_delay = int(value)
            return True

        # High alarm settings
        elif path == '/Alarms/High/Enable':
            self._high_alarm_enabled = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/High/Active':
            self._high_alarm_active = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/High/Restore':
            self._high_alarm_restore = int(value)
            self._update_level_alarms()
            return True
        elif path == '/Alarms/High/Delay':
            self._high_alarm_delay = int(value)
            return True

        return False

    def _update_level_alarms(self):
        """Update alarm states based on current tank level and sensor status.

        This is the key method that triggers Venus OS notifications.
        The venus-platform monitors /Alarms/Low/State and /Alarms/High/State
        and creates notifications when these change.

        When sensor has a fault (Status != OK), we set low alarm state to 2
        to trigger a sensor fault notification.

        During startup settling period, level-based alarms are not triggered to prevent
        false alerts while sensors stabilize. Sensor faults are always reported immediately.
        """
        # If sensor is not OK, trigger a sensor fault alarm immediately
        # This is done by setting the low alarm state to 2 (Alarm)
        # venus-platform will create a notification for this
        # Sensor faults bypass the startup settling period
        if self._status != Status.OK:
            new_low_state = 2  # Alarm
            new_high_state = 0  # Clear high alarm when sensor is faulty

            if self._low_alarm_state != new_low_state:
                logger.warning(f"Tank {self._id} ({self._name}): Sensor fault - setting alarm state to {new_low_state}")
                self._low_alarm_state = new_low_state
                self._dbus_set('/Alarms/Low/State', self._low_alarm_state)

            if self._high_alarm_state != new_high_state:
                self._high_alarm_state = new_high_state
                self._dbus_set('/Alarms/High/State', self._high_alarm_state)

            return

        # During startup settling period, don't trigger level-based alarms
        # This prevents false alerts when sensors take time to initialize
        if self._startup_readings_count < self._startup_settling_readings:
            logger.debug(f"Tank {self._id} ({self._name}): Skipping alarm check during startup settling (reading {self._startup_readings_count + 1}/{self._startup_settling_readings})")
            return

        # Sensor is OK - evaluate level-based alarms
        level = self._level

        # Low level alarm evaluation
        if self._low_alarm_enabled:
            if level <= self._low_alarm_active:
                # Level is at or below active threshold - trigger alarm
                new_low_state = 2  # Alarm
            elif level >= self._low_alarm_restore:
                # Level is at or above restore threshold - clear alarm
                new_low_state = 0  # Ok
            else:
                # Level is between thresholds - maintain current state
                new_low_state = self._low_alarm_state
        else:
            # Low alarm disabled
            new_low_state = 0

        # High level alarm evaluation
        if self._high_alarm_enabled:
            if level >= self._high_alarm_active:
                # Level is at or above active threshold - trigger alarm
                new_high_state = 2  # Alarm
            elif level <= self._high_alarm_restore:
                # Level is at or below restore threshold - clear alarm
                new_high_state = 0  # Ok
            else:
                # Level is between thresholds - maintain current state
                new_high_state = self._high_alarm_state
        else:
            # High alarm disabled
            new_high_state = 0

        # Update D-Bus if states changed
        if self._low_alarm_state != new_low_state:
            logger.info(f"Tank {self._id} ({self._name}): Low alarm state changed from {self._low_alarm_state} to {new_low_state} (level={level:.1f}%, threshold={self._low_alarm_active}%)")
            self._low_alarm_state = new_low_state
            self._dbus_set('/Alarms/Low/State', self._low_alarm_state)

        if self._high_alarm_state != new_high_state:
            logger.info(f"Tank {self._id} ({self._name}): High alarm state changed from {self._high_alarm_state} to {new_high_state} (level={level:.1f}%, threshold={self._high_alarm_active}%)")
            self._high_alarm_state = new_high_state
            self._dbus_set('/Alarms/High/State', self._high_alarm_state)

    def _attach_to_settings(self, settings_base, event_callback):
        # SettingsDevice requires a raw dbus connection. 
        # We create a dedicated connection for settings before the D-Bus service.
        # If no usable bus is available (for example in unit tests), provide a
        # lightweight dummy bus that implements the minimal API used by
        # SettingsDevice so it can initialise without blocking.
        bus = self._settings_dbus_connection
        
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
        """Handle setting changes from Venus OS GUI or other sources.
        
        This callback is triggered when any setting changes via the
        com.victronenergy.settings D-Bus service. Changes are synced
        to the tank service D-Bus paths.
        """
        # Accept either signature: (setting, new) or (setting, old, new)
        if len(args) == 1:
            new_value = args[0]
        elif len(args) >= 2:
            new_value = args[1]
        else:
            return

        logger.info(f"Tank {self._id} ({self._name}): Setting '{setting}' changed to {new_value}")

        if setting == 'scale':
            self._scale = new_value
        elif setting == 'offset':
            self._offset = new_value
        elif setting == 'capacity':
            self._tank_capacity = new_value
            self._dbus_set('/Capacity', float(new_value))
            # Recalculate remaining
            self._remaining = (self._level / 100.0) * self._tank_capacity
            self._dbus_set('/Remaining', float(round(self._remaining, 4)))
        elif setting == 'fluid_type':
            self._fluid_type = FluidType(new_value)
            self._dbus_set('/FluidType', self._fluid_type.value)
            logger.info(f"Tank {self._id}: Fluid type changed to {self._fluid_type.name}")
        elif setting == 'custom_name':
            # Update the name and push to the /CustomName D-Bus path so the
            # GUI stays in sync when the setting is changed from another source.
            self._name = str(new_value) if new_value else ''
            self._dbus_set('/CustomName', self._name)
            logger.info(f"Tank {self._id}: Custom name changed to '{self._name}'")
        elif setting == 'raw_value_empty':
            # new_value is the ADC voltage when the tank is *empty*.
            # Convert voltage → resistance via the voltage-divider formula so
            # that _resistance_to_percentage() uses the correct calibration.
            if isinstance(new_value, (int, float)) and 0.0 <= float(new_value) < self._reference_voltage:
                self._sensor_min = round(self._voltage_to_resistance(float(new_value)), 4)
                logger.info(
                    f"Tank {self._id}: Calibrated empty point: "
                    f"{new_value}V → {self._sensor_min:.4f}Ω"
                )
            else:
                logger.warning(
                    f"Tank {self._id}: raw_value_empty {new_value!r} is outside "
                    f"[0, {self._reference_voltage}) V – ignoring"
                )
        elif setting == 'raw_value_full':
            # new_value is the ADC voltage when the tank is *full*.
            if isinstance(new_value, (int, float)) and 0.0 < float(new_value) < self._reference_voltage:
                self._sensor_max = round(self._voltage_to_resistance(float(new_value)), 4)
                logger.info(
                    f"Tank {self._id}: Calibrated full point: "
                    f"{new_value}V → {self._sensor_max:.4f}Ω"
                )
            else:
                logger.warning(
                    f"Tank {self._id}: raw_value_full {new_value!r} is outside "
                    f"(0, {self._reference_voltage}) V – ignoring"
                )
        elif setting == 'device_instance':
            # DeviceInstance changed in GUI - update D-Bus and internal state
            if new_value != self._device_instance:
                logger.info(f"Tank {self._id} ({self._name}): DeviceInstance changed from {self._device_instance} to {new_value}")
                self._device_instance = int(new_value)
                # Update D-Bus path - note this doesn't change the service name
                self._dbus_set('/DeviceInstance', self._device_instance)
        elif setting == 'instance':
            # Instance format is "tank:N" - used for VRM integration
            logger.info(f"Tank {self._id}: Instance set to '{new_value}'")

    def _set_status(self, status):
        """Update sensor status and trigger alarm updates.

        When status changes to a fault state, this will trigger
        /Alarms/Low/State to be set to 2 (Alarm), which venus-platform
        will pick up and create a notification for.

        /Connected is kept in sync with sensor health so that VRM Portal
        correctly shows the device as offline when a fault is detected.
        """
        self._status = status
        self._dbus_set('/Status', self._status.value)

        # /Connected: 1 = operating normally, 0 = any hardware fault.
        # Venus OS and the VRM Portal use this flag to distinguish a device
        # that is present but broken from one that has never appeared.
        self._dbus_set('/Connected', 1 if status == Status.OK else 0)

        # Update legacy /Alarm path (kept for compatibility)
        # Note: This path is NOT monitored by venus-platform for tank notifications
        # We keep it for backward compatibility and debugging
        if status == Status.OK:
            self._alarm = 0
        elif status == Status.DISCONNECTED:
            self._alarm = 2
        elif status == Status.SHORT_CIRCUITED:
            self._alarm = 2
        elif status == Status.REVERSE_POLARITY:
            self._alarm = 2
        else:
            self._alarm = 1

        self._dbus_set('/Alarm', self._alarm)

        # Update level alarms - this is what triggers Venus OS notifications
        # When sensor is faulty, _update_level_alarms will set alarm state to 2
        self._update_level_alarms()

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
            logger.debug(f"Sysfs path not found: {self._sysfs_path}, falling back to SMBus")
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
            # Use the mapped channel (iio_channel) so that channel_map applies
            # consistently whether the sysfs IIO path or SMBus fallback is used.
            channel = self._iio_channel
            if channel not in MUX:
                channel = 0
            mux = MUX[channel]

            with SMBus(self._i2c_bus) as bus:
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

                # Single-shot conversion: write config, wait for result, read.
                # One read per call is sufficient – the 15 ms sleep already covers
                # the full ADS1115 conversion time at 128 SPS (~8 ms).  The old
                # 3-attempt retry loop was masking real wiring issues by silently
                # discarding signed (negative) raw values; now we return the proper
                # two's-complement signed value and let the conversion chain decide
                # how to handle it (near-zero → EMPTY, truly negative → SHORT_CIRCUITED
                # via the stability check).
                config_msb = (1 << 7) | (mux << 4) | (pga_bits << 1)
                config_lsb = 0x03 | (7 << 5)  # MODE=single, DR=128SPS
                # ADS1115 expects MSB first when writing config: [MSB, LSB]
                bus.write_i2c_block_data(addr, 0x01, [config_msb, config_lsb])
                time.sleep(0.015)  # ~8 ms conversion time at 128 SPS + margin
                # Read conversion: device returns [MSB, LSB] big-endian
                data = bus.read_i2c_block_data(addr, 0x00, 2)
                raw = (data[0] << 8) | data[1]
                # ADS1115 output is two's-complement signed 16-bit.
                # Convert from unsigned representation to signed so that
                # voltages below 0 V (reverse bias, miswiring) are correctly
                # reflected downstream instead of being retried endlessly.
                if raw > 32767:
                    raw -= 65536
                return raw
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

    def _check_reading_stability(self, resistance):
        """Check if readings indicate a disconnected/floating sensor.

        This check is designed to detect a truly disconnected ADC pin where readings
        are completely erratic (random noise). It should NOT trigger during normal
        sensor movement or tank level changes.

        A disconnected sensor shows:
        - Readings jumping wildly between extremes (not trending)
        - Values outside the sensor's valid range
        - Very high relative variance that doesn't settle

        Returns True if stable (connected), False if unstable (likely disconnected).
        """
        # Add to history
        self._resistance_history.append(resistance)
        if len(self._resistance_history) > self._history_size:
            self._resistance_history.pop(0)

        # Need at least 5 readings for reliable detection
        if len(self._resistance_history) < 5:
            return True  # Assume stable until we have enough data

        values = self._resistance_history

        # Check 1: Are any readings completely out of range?
        # A connected sensor should never read negative or extremely high values
        for v in values:
            if v < 0 or v > self._sensor_max * 20:  # Allow some headroom
                logger.warning(f"Tank {self._id} ({self._name}): Out-of-range reading detected ({v:.2f}Ω)")
                return False

        # Check 2: Check if readings are "bimodal" (jumping between two extremes)
        # This indicates a floating pin, not a sensor being moved
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val
        mean = sum(values) / len(values)

        # If all readings are within a reasonable range, sensor is connected
        # A floating pin would show readings jumping across the entire ADC range
        # For our sensor (0-190Ω), a range of <50Ω indicates stable readings
        MAX_RANGE_FOR_STABLE = 50.0  # Ohms - if readings vary less than this, it's stable

        if range_val < MAX_RANGE_FOR_STABLE:
            return True

        # Check 3: If range is larger, check if readings are trending (legitimate movement)
        # vs random jumping (disconnected)
        # Count sign changes in differences - random noise has many sign changes
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        sign_changes = sum(1 for i in range(len(diffs)-1) 
                          if (diffs[i] > 0) != (diffs[i+1] > 0))

        # If there are many sign changes, readings are erratic (disconnected)
        # A sensor being moved will trend in one direction
        MAX_SIGN_CHANGES = len(values) - 2  # Allow one sign change per transition

        if sign_changes > MAX_SIGN_CHANGES:
            logger.warning(f"Tank {self._id} ({self._name}): Erratic readings detected (range={range_val:.1f}Ω, sign_changes={sign_changes})")
            return False

        return True

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
        """Update sensor reading and alarm states.

        This method:
        1. Reads the ADC value
        2. Converts to tank level
        3. Updates D-Bus paths
        4. Updates alarm states (which triggers Venus OS notifications)
        """
        raw_value = self._read_adc_raw()
        if raw_value is None:
            self._set_status(Status.DISCONNECTED)
            return

        try:
            raw_value = raw_value * self._scale + self._offset
            voltage = self._raw_to_voltage(raw_value)
            resistance = self._voltage_to_resistance(voltage)

            # Detect sensor fault conditions
            # 1. Open circuit (disconnected): resistance is infinity
            if resistance == float('inf') or resistance > self._sensor_max * 10:
                self._level = 0.0
                self._remaining = 0.0
                self._dbus_set("/Level", 0.0)
                self._dbus_set("/Remaining", 0.0)
                if self._status != Status.DISCONNECTED:
                    logger.warning(f"Tank {self._id} ({self._name}): Open circuit detected (resistance={resistance})")
                    self._set_status(Status.DISCONNECTED)
                return

            # 2. Short circuit or reverse polarity: resistance is negative or near zero
            if resistance < 0:
                self._level = 0.0
                self._remaining = 0.0
                self._dbus_set("/Level", 0.0)
                self._dbus_set("/Remaining", 0.0)
                if self._status != Status.SHORT_CIRCUITED:
                    logger.warning(f"Tank {self._id} ({self._name}): Short circuit/reverse polarity detected (resistance={resistance})")
                    self._set_status(Status.SHORT_CIRCUITED)
                return

            # 3. Check for unstable readings (floating/disconnected sensor)
            if not self._check_reading_stability(resistance):
                self._level = 0.0
                self._remaining = 0.0
                self._dbus_set("/Level", 0.0)
                self._dbus_set("/Remaining", 0.0)
                if self._status != Status.DISCONNECTED:
                    logger.warning(f"Tank {self._id} ({self._name}): Unstable readings detected - sensor likely disconnected")
                    self._set_status(Status.DISCONNECTED)
                return

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
            else:
                # Sensor is OK - update level-based alarms
                self._update_level_alarms()

            # Increment startup counter after successful reading
            if self._startup_readings_count < self._startup_settling_readings:
                self._startup_readings_count += 1
                if self._startup_readings_count == self._startup_settling_readings:
                    logger.info(f"Tank {self._id} ({self._name}): Startup settling period complete - alarms now enabled")

            logger.info(f"Tank '{self._name}' [id={self._id}, ch={self._channel}, instance={self._device_instance}]: raw_adc={raw_value}, voltage={voltage:.6f}V, resistance={resistance:.2f}Ω, level={self._level:.1f}%, remaining={self._remaining:.4f}m3")
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


# Mock class reference for runtime type checking
try:
    from unittest.mock import Mock as _UMock
except ImportError:
    # Fallback for environments without unittest.mock
    class _UMock:
        pass
