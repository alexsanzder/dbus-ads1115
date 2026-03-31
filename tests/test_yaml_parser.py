"""
Tests for YAML parser (parse_simple_yaml function).
"""

import pytest
from dbus_ads1115.dbus_ads1115 import parse_simple_yaml


class TestYamlParserBasic:
    """Test basic YAML parsing functionality."""

    def test_parse_simple_key_value(self):
        """Test parsing simple key-value pairs."""
        content = "key1: value1\nkey2: value2"
        result = parse_simple_yaml(content)
        assert result == {'key1': 'value1', 'key2': 'value2'}

    def test_parse_boolean_true(self):
        """Test parsing boolean true values."""
        content = "enabled: true"
        result = parse_simple_yaml(content)
        assert result['enabled'] is True

    def test_parse_boolean_false(self):
        """Test parsing boolean false values."""
        content = "enabled: false"
        result = parse_simple_yaml(content)
        assert result['enabled'] is False

    def test_parse_integer(self):
        """Test parsing integer values."""
        content = "count: 5"
        result = parse_simple_yaml(content)
        assert result['count'] == 5

    def test_parse_float(self):
        """Test parsing float values."""
        content = "voltage: 3.3"
        result = parse_simple_yaml(content)
        assert result['voltage'] == 3.3

    def test_parse_string(self):
        """Test parsing string values."""
        content = 'name: "My Sensor"'
        result = parse_simple_yaml(content)
        assert result['name'] == 'My Sensor'

    def test_parse_quoted_string_single(self):
        """Test parsing single-quoted strings."""
        content = "name: 'My Sensor'"
        result = parse_simple_yaml(content)
        assert result['name'] == 'My Sensor'

    def test_parse_unquoted_string(self):
        """Test parsing unquoted strings."""
        content = "name: MySensor"
        result = parse_simple_yaml(content)
        assert result['name'] == 'MySensor'


class TestYamlParserNested:
    """Test parsing nested YAML structures."""

    def test_parse_nested_dict(self):
        """Test parsing nested dictionaries."""
        content = """
i2c:
  bus: 1
  address: "0x48"
"""
        result = parse_simple_yaml(content)
        assert result == {'i2c': {'bus': 1, 'address': '0x48'}}

    def test_parse_deeply_nested(self):
        """Test parsing deeply nested structures."""
        content = """
level1:
  level2:
    level3: value
"""
        result = parse_simple_yaml(content)
        assert result == {'level1': {'level2': {'level3': 'value'}}}

    def test_parse_mixed_types_nested(self):
        """Test parsing mixed types in nested structures."""
        content = """
i2c:
  bus: 1
  address: "0x48"
  enabled: true
  count: 5
"""
        result = parse_simple_yaml(content)
        expected = {
            'i2c': {
                'bus': 1,
                'address': '0x48',
                'enabled': True,
                'count': 5
            }
        }
        assert result == expected


class TestYamlParserLists:
    """Test parsing list structures."""

    def test_parse_simple_list(self):
        """Test parsing a simple list."""
        content = """
sensors:
  - name: Sensor1
  - name: Sensor2
"""
        result = parse_simple_yaml(content)
        assert isinstance(result['sensors'], list)
        assert len(result['sensors']) == 2
        assert result['sensors'][0] == {'name': 'Sensor1'}
        assert result['sensors'][1] == {'name': 'Sensor2'}

    def test_parse_list_with_values(self):
        """Test parsing list items with values."""
        content = """
sensors:
  - name: Sensor1
    channel: 0
  - name: Sensor2
    channel: 1
"""
        result = parse_simple_yaml(content)
        assert result['sensors'][0] == {'name': 'Sensor1', 'channel': 0}
        assert result['sensors'][1] == {'name': 'Sensor2', 'channel': 1}

    def test_parse_empty_list(self):
        """Test parsing an empty list."""
        content = "sensors:\n"
        result = parse_simple_yaml(content)
        assert result == {'sensors': []}


class TestYamlParserComments:
    """Test comment handling in YAML."""

    def test_ignore_inline_comments(self):
        """Test that inline comments are ignored."""
        content = "key: value # This is a comment"
        result = parse_simple_yaml(content)
        assert result == {'key': 'value'}

    def test_ignore_full_line_comments(self):
        """Test that full-line comments are ignored."""
        content = "# This is a comment\nkey: value"
        result = parse_simple_yaml(content)
        assert result == {'key': 'value'}

    def test_ignore_multiple_comments(self):
        """Test that multiple comments are ignored."""
        content = """
# Comment 1
key1: value1 # Comment 2
# Comment 3
key2: value2
"""
        result = parse_simple_yaml(content)
        assert result == {'key1': 'value1', 'key2': 'value2'}


class TestYamlParserEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_string(self):
        """Test parsing empty string."""
        result = parse_simple_yaml("")
        assert result == {}

    def test_whitespace_only(self):
        """Test parsing whitespace-only string."""
        result = parse_simple_yaml("   \n\n   \n")
        assert result == {}

    def test_empty_value(self):
        """Test parsing key with empty value."""
        content = "key:"
        result = parse_simple_yaml(content)
        assert result == {'key': {}}

    def test_list_item_empty_value(self):
        """Test parsing list item with empty value."""
        content = """
sensors:
  - name:
"""
        result = parse_simple_yaml(content)
        assert result == {'sensors': [{'name': {}}]}

    def test_multiple_empty_values(self):
        """Test parsing multiple keys with empty values."""
        content = """
key1:
key2:
key3:
"""
        result = parse_simple_yaml(content)
        assert result == {'key1': {}, 'key2': {}, 'key3': {}}

    def test_indented_lists(self):
        """Test properly indented list items."""
        content = """
sensors:
  - name: Sensor1
    channel: 0
  - name: Sensor2
    channel: 1
"""
        result = parse_simple_yaml(content)
        assert len(result['sensors']) == 2
        assert result['sensors'][0]['channel'] == 0
        assert result['sensors'][1]['channel'] == 1


class TestYamlParserRealWorld:
    """Test with real-world configuration examples."""

    def test_complete_sensor_config(self):
        """Test parsing complete sensor configuration."""
        content = """
# ADS1115 configuration
i2c:
  bus: 1
  address: "0x48"
  reference_voltage: 3.3

sensors:
  - type: tank
    name: "Fresh Water Tank"
    channel: 0
    fixed_resistor: 220
    sensor_min: 0.1
    sensor_max: 13.55
    tank_capacity: 0.07
    fluid_type: fresh_water
    update_interval: 5000
"""
        result = parse_simple_yaml(content)
        
        assert result['i2c']['bus'] == 1
        assert result['i2c']['address'] == '0x48'
        assert result['i2c']['reference_voltage'] == 3.3
        
        assert isinstance(result['sensors'], list)
        assert len(result['sensors']) == 1
        
        sensor = result['sensors'][0]
        assert sensor['type'] == 'tank'
        assert sensor['name'] == 'Fresh Water Tank'
        assert sensor['channel'] == 0
        assert sensor['fixed_resistor'] == 220
        assert sensor['sensor_min'] == 0.1
        assert sensor['sensor_max'] == 13.55
        assert sensor['tank_capacity'] == 0.07
        assert sensor['fluid_type'] == 'fresh_water'
        assert sensor['update_interval'] == 5000

    def test_multiple_sensors_config(self):
        """Test parsing multiple sensors configuration."""
        content = """
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
        result = parse_simple_yaml(content)
        
        assert len(result['sensors']) == 2
        assert result['sensors'][0]['name'] == 'Tank 1'
        assert result['sensors'][0]['fluid_type'] == 'fresh_water'
        assert result['sensors'][1]['name'] == 'Tank 2'
        assert result['sensors'][1]['fluid_type'] == 'waste_water'
