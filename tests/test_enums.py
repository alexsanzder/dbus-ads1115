"""
Tests for enum definitions.
"""

import pytest
from dbus_ads1115.enums import FluidType, Status, TemperatureType


class TestFluidType:
    """Test FluidType enum values."""

    def test_fuel_value(self):
        """Test FUEL enum value."""
        assert FluidType.FUEL.value == 0

    def test_fresh_water_value(self):
        """Test FRESH_WATER enum value."""
        assert FluidType.FRESH_WATER.value == 1

    def test_waste_water_value(self):
        """Test WASTE_WATER enum value."""
        assert FluidType.WASTE_WATER.value == 2

    def test_live_well_value(self):
        """Test LIVE_WELL enum value."""
        assert FluidType.LIVE_WELL.value == 3

    def test_oil_value(self):
        """Test OIL enum value."""
        assert FluidType.OIL.value == 4

    def test_black_water_value(self):
        """Test BLACK_WATER enum value."""
        assert FluidType.BLACK_WATER.value == 5

    def test_fluid_type_count(self):
        """Test that we have all expected fluid types."""
        assert len(FluidType) == 6

    def test_fluid_type_uniqueness(self):
        """Test that all fluid type values are unique."""
        values = [ft.value for ft in FluidType]
        assert len(values) == len(set(values))

    def test_fluid_type_comparison(self):
        """Test enum comparison operators."""
        assert FluidType.FRESH_WATER == FluidType.FRESH_WATER
        assert FluidType.FRESH_WATER != FluidType.FUEL
        # Note: Python 3.11+ enums don't support < operator for comparison
        # We test value comparison instead
        assert FluidType.FUEL.value < FluidType.WASTE_WATER.value

    def test_fluid_type_iteration(self):
        """Test that we can iterate over fluid types."""
        fluid_types = list(FluidType)
        assert len(fluid_types) == 6
        assert FluidType.FUEL in fluid_types
        assert FluidType.BLACK_WATER in fluid_types


class TestStatus:
    """Test Status enum values."""

    def test_ok_value(self):
        """Test OK status value."""
        assert Status.OK.value == 0

    def test_disconnected_value(self):
        """Test DISCONNECTED status value."""
        assert Status.DISCONNECTED.value == 1

    def test_short_circuited_value(self):
        """Test SHORT_CIRCUITED status value."""
        assert Status.SHORT_CIRCUITED.value == 2

    def test_reverse_polarity_value(self):
        """Test REVERSE_POLARITY status value."""
        assert Status.REVERSE_POLARITY.value == 3

    def test_unknown_value(self):
        """Test UNKNOWN status value."""
        assert Status.UNKNOWN.value == 4

    def test_status_count(self):
        """Test that we have all expected statuses."""
        assert len(Status) == 5

    def test_status_uniqueness(self):
        """Test that all status values are unique."""
        values = [s.value for s in Status]
        assert len(values) == len(set(values))

    def test_status_comparison(self):
        """Test enum comparison operators."""
        assert Status.OK == Status.OK
        assert Status.OK != Status.DISCONNECTED
        # Note: Python 3.11+ enums don't support < operator for comparison
        # We test value comparison instead
        assert Status.OK.value < Status.SHORT_CIRCUITED.value

    def test_status_iteration(self):
        """Test that we can iterate over statuses."""
        statuses = list(Status)
        assert len(statuses) == 5
        assert Status.OK in statuses
        assert Status.UNKNOWN in statuses


class TestTemperatureType:
    """Test TemperatureType enum values."""

    def test_battery_value(self):
        """Test BATTERY temperature type value."""
        assert TemperatureType.BATTERY.value == 0

    def test_fridge_value(self):
        """Test FRIDGE temperature type value."""
        assert TemperatureType.FRIDGE.value == 1

    def test_generic_value(self):
        """Test GENERIC temperature type value."""
        assert TemperatureType.GENERIC.value == 2

    def test_temperature_type_count(self):
        """Test that we have all expected temperature types."""
        assert len(TemperatureType) == 3

    def test_temperature_type_uniqueness(self):
        """Test that all temperature type values are unique."""
        values = [tt.value for tt in TemperatureType]
        assert len(values) == len(set(values))

    def test_temperature_type_comparison(self):
        """Test enum comparison operators."""
        assert TemperatureType.BATTERY == TemperatureType.BATTERY
        assert TemperatureType.BATTERY != TemperatureType.FRIDGE
        # Note: Python 3.11+ enums don't support < operator for comparison
        # We test value comparison instead
        assert TemperatureType.BATTERY.value < TemperatureType.GENERIC.value

    def test_temperature_type_iteration(self):
        """Test that we can iterate over temperature types."""
        temp_types = list(TemperatureType)
        assert len(temp_types) == 3
        assert TemperatureType.BATTERY in temp_types
        assert TemperatureType.GENERIC in temp_types


class TestEnumStringRepresentation:
    """Test enum string representations."""

    def test_fluid_type_string(self):
        """Test FluidType string representation."""
        assert str(FluidType.FRESH_WATER) == 'FluidType.FRESH_WATER'

    def test_status_string(self):
        """Test Status string representation."""
        assert str(Status.OK) == 'Status.OK'

    def test_temperature_type_string(self):
        """Test TemperatureType string representation."""
        assert str(TemperatureType.BATTERY) == 'TemperatureType.BATTERY'
