# Testing Documentation for dbus-ads1115

## Overview

This document describes the testing infrastructure and how to run tests locally and via GitHub Actions.

## Test Structure

```
tests/
├── __init__.py                    # Test package marker
├── conftest.py                     # pytest fixtures (mocks, shared setup)
├── test_yaml_parser.py              # YAML parsing tests (25 tests)
├── test_enums.py                  # Enum tests (29 tests)
├── test_tank_sensor.py             # TankSensor tests (53 tests - requires D-Bus)
└── test_sensor_manager.py           # SensorManager tests (13 tests - requires D-Bus)
```

## Test Statistics

- **Total Test Files:** 5
- **Total Test Cases:** 120
- **Passing Tests:** 54 (YAML parser + enums)
- **Tests Requiring D-Bus:** 66 (TankSensor + SensorManager)

## Running Tests Locally

### Prerequisites

```bash
# Install pytest and dependencies
pip3 install pytest pytest-mock

# (Optional) Install D-Bus dependencies for Linux
# Not required on macOS due to mocking
```

### Run All Tests

```bash
cd /path/to/dbus-ads1115
pytest tests/ -v
```

### Run Specific Test File

```bash
# Run only YAML parser tests
pytest tests/test_yaml_parser.py -v

# Run only enum tests
pytest tests/test_enums.py -v
```

### Run Specific Test

```bash
# Run a specific test
pytest tests/test_yaml_parser.py::TestYamlParserBasic::test_parse_simple_key_value -v

# Run tests matching a pattern
pytest tests/test_enums.py -k "test_fluid" -v
```

### Quick Test Summary

```bash
# Run without verbose output (summary only)
pytest tests/ -q

# Run with short traceback on failure
pytest tests/ --tb=short

# Run and stop on first failure
pytest tests/ -x
```

## Test Coverage

### YAML Parser Tests (25 tests)

**Purpose:** Validate custom YAML parser works without PyYAML dependency

**Test Areas:**
- ✓ Simple key-value pairs
- ✓ Boolean, integer, float, string parsing
- ✓ Nested dictionaries
- ✓ Lists with dictionaries
- ✓ Comment handling (inline, full-line, multiple)
- ✓ Edge cases (empty values, whitespace, indentation)
- ✓ Real-world sensor configurations

**Status:** ✅ **ALL PASSING (25/25)**

### Enum Tests (29 tests)

**Purpose:** Ensure enum values match VenusOS NMEA2000 specifications

**Test Areas:**
- ✓ FluidType values (FUEL=0, FRESH_WATER=1, etc.)
- ✓ Status values (OK=0, DISCONNECTED=1, etc.)
- ✓ TemperatureType values (BATTERY=0, FRIDGE=1, etc.)
- ✓ Enum value uniqueness
- ✓ Enum iteration and comparison

**Status:** ✅ **ALL PASSING (29/29)**

### TankSensor Tests (53 tests)

**Purpose:** Test sensor initialization, conversions, and state management

**Test Areas:**
- Initialization with full/minimal config
- I2C bus/address inheritance
- Fluid type mapping
- Sysfs path construction
- Voltage/resistance/percentage conversions
- Update method with ADC readings
- D-Bus value updates
- Settings handling (scale, offset)
- Status management (OK, DISCONNECTED, UNKNOWN)
- Error handling (file read, conversion errors)
- Scale and offset application

**Status:** ⚠️ **Requires D-Bus mocking** - Tests need enhanced D-Bus mock setup

### SensorManager Tests (13 tests)

**Purpose:** Test sensor orchestration and configuration fallback

**Test Areas:**
- Initialization with valid/invalid config
- I2C config fallback (global vs sensor-specific)
- Multiple sensor creation
- Update method calling all sensors
- Error handling (missing files, invalid YAML)

**Status:** ⚠️ **Requires D-Bus mocking** - Tests need enhanced D-Bus mock setup

## Fixtures (conftest.py)

### Available Fixtures

1. **mock_dbus** - Mock D-Bus connection
2. **mock_glib** - Mock GLib main loop
3. **mock_config** - Valid sensor configuration
4. **mock_config_file** - Temporary config file for testing
5. **mock_i2c_device** - Mock I2C sysfs device files
6. **minimal_config** - Minimal sensor config (tests defaults)
7. **invalid_config** - Invalid config for error testing
8. **multi_sensor_config** - Multiple sensors configuration

## Platform-Specific Notes

### macOS (Development)

- D-Bus module is mocked in conftest.py for macOS compatibility
- Tests run without actual D-Bus system
- All YAML parser and enum tests pass successfully
- TankSensor and SensorManager tests require enhanced D-Bus mocking

### Linux (VenusOS)

- Tests should run with actual D-Bus system (if desired)
- Integration tests can use real I2C devices
- For unit tests, prefer mocking for speed and reliability

## GitHub Actions

### Workflow Triggers

- Pull requests to `main` branch
- Pushes to `main` branch
- Release creation

### Test Matrix

```yaml
python-version: [3.8, 3.9, 3.10, 3.11, 3.12]
os: [ubuntu-latest]
```

### Workflow Steps

1. Checkout code
2. Set up Python (multiple versions)
3. Install test dependencies
4. Run pytest with verbose output
5. Upload test results (if any failures)

### Release Protection

When creating a GitHub release:
- Tests run automatically
- Release is blocked if tests fail
- Ensures only tested code is released

## Troubleshooting

### Tests Fail with Import Errors

**Problem:** `ModuleNotFoundError: No module named 'dbus'`

**Solution:** Ensure conftest.py has D-Bus mocking enabled (check `sys.modules['dbus']` setup)

### Tests Fail with Mock Errors

**Problem:** `AttributeError: Mock object has no attribute '...'`

**Solution:** Verify fixture is applied or mock is configured correctly in conftest.py

### Tests Pass Locally But Fail on GitHub Actions

**Problem:** Environment differences between local and CI

**Solution:**
1. Check Python version differences
2. Verify test dependencies are installed
3. Review GitHub Actions logs for specific errors
4. Add debug output to failing tests

### Test Execution Too Slow

**Problem:** Tests take too long to run

**Solution:**
1. Use mock fixtures instead of real D-Bus
2. Run specific test files instead of all tests
3. Use `-x` flag to stop on first failure
4. Consider parallel test execution

## Best Practices

### Writing New Tests

1. **Use descriptive test names:**
   ```python
   def test_parse_boolean_true(self):  # Good
   def test_parse_bool_true(self):     # Less clear
   ```

2. **Follow AAA pattern:**
   - **Arrange:** Setup test data and mocks
   - **Act:** Call the function being tested
   - **Assert:** Verify expected behavior

3. **Use fixtures for shared setup:**
   ```python
   def test_something(self, mock_config):
       sensor = TankSensor(mock_config)
       # ... test code ...
   ```

4. **Test both success and failure paths:**
   ```python
   def test_with_valid_input(self, mock_config):
       # Test success path
   
   def test_with_invalid_input(self, invalid_config):
       # Test error handling
   ```

5. **Add docstrings to test classes:**
   ```python
   class TestYamlParserBasic:
       """Test basic YAML parsing functionality."""
   ```

## Continuous Integration

### Test Before Pushing

```bash
# Run tests locally before committing
pytest tests/ -q

# If all tests pass:
git add .
git commit -m "Add tests and CI/CD"

# Push and let GitHub Actions run
git push origin main
```

### Monitor CI Results

1. Go to GitHub repository
2. Click "Actions" tab
3. View workflow runs
4. Check test results for any failures
5. Review logs for failing tests

## Release Checklist

Before creating a new release:

- [ ] All tests pass locally
- [ ] Tests pass on all Python versions (3.8-3.12)
- [ ] GitHub Actions run successfully
- [ ] No test failures in CI/CD
- [ ] Code review completed
- [ ] Documentation updated (if needed)

After creating a release:

- [ ] Release marked as "Latest"
- [ ] GitHub Actions verified release with tests
- [ ] Package tested on VenusOS device
- [ ] Users can install via PackageManager

## Future Improvements

### Short-Term

1. ✅ Implement enhanced D-Bus mocking for TankSensor/SensorManager tests
2. ✅ Add integration tests with mock I2C devices
3. ✅ Test coverage reporting (optional)
4. ✅ Property-based testing with Hypothesis (optional)

### Long-Term

1. Add performance benchmarks for update() method
2. Create end-to-end tests with real VenusOS environment
3. Add stress tests for long-running stability
4. Implement test data generation for edge case discovery
