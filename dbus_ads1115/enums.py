from enum import Enum


class FluidType(Enum):
    """Note that the FluidType enumeration is kept in sync with NMEA2000 definitions."""

    FUEL = 0
    FRESH_WATER = 1
    WASTE_WATER = 2
    LIVE_WELL = 3
    OIL = 4
    BLACK_WATER = 5  # Sewage


class Status(Enum):
    """Enum to describe Sensor Status."""

    OK = 0
    DISCONNECTED = 1
    SHORT_CIRCUITED = 2
    REVERSE_POLARITY = 3
    UNKNOWN = 4


class TemperatureType(Enum):
    """Enum for type of temperature sensor."""

    BATTERY = 0
    FRIDGE = 1
    GENERIC = 2
