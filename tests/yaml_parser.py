"""
YAML parser for dbus-ads1115 tests.
This module contains the parse_simple_yaml function without D-Bus dependencies.
"""

import re


def parse_simple_yaml(content):
    """
    Parse simple YAML format without requiring PyYAML.
    
    Supports:
    - Key-value pairs
    - Nested dictionaries
    - Lists with dictionaries
    - Boolean values (true/false)
    - Numeric values (int, float)
    - String values (quoted or unquoted)
    - Comments (inline and full-line)
    """
    def parse_value(v):
        v = v.strip()
        if v.lower() == 'true': return True
        if v.lower() == 'false': return False
        try: return int(v)
        except ValueError:
            try: return float(v)
            except ValueError: return v.strip('"\'')
    
    config = {}
    stack = [(None, config)]
    for line in content.split('\n'):
        line = line.split('#')[0].rstrip()
        if not line: continue
        indent = len(line) - len(line.lstrip())
        level = indent // 2
        stripped = line.strip()
        while len(stack) > level + 1: stack.pop()
        _, current = stack[-1]
        
        m = re.match(r'^(\w+)\s*:\s*$', stripped)
        if m:
            name = m.group(1)
            current[name] = [] if name == 'sensors' else {}
            stack.append((name, current[name]))
            continue
            
        m = re.match(r'^-\s*(\w+)\s*:\s*(.*)$', stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            item = {key: parse_value(val)} if val else {key: {}}
            current.append(item)
            stack.append((key, item))
            continue
            
        m = re.match(r'^(\w+)\s*:\s*(.*)$', stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            current[key] = parse_value(val) if val else {}
    return config
