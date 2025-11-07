"""Tests for condition validation."""

from __future__ import annotations

import pytest
from homeassistant.core import State

from custom_components.fallback_sensors.conditions import ConditionValidator
from custom_components.fallback_sensors.const import (
    CONDITION_TYPE_RANGE,
    CONDITION_TYPE_REGEX,
    CONF_CONDITION_MAX,
    CONF_CONDITION_MIN,
    CONF_CONDITION_PATTERN,
    CONF_CONDITION_TYPE,
)


def test_no_conditions_always_valid() -> None:
    """Test that no conditions means always valid."""
    validator = ConditionValidator(None)
    state = State("sensor.test", "any_value")
    assert validator.is_valid(state)


def test_empty_conditions_always_valid() -> None:
    """Test that empty conditions list means always valid."""
    validator = ConditionValidator([])
    state = State("sensor.test", "any_value")
    assert validator.is_valid(state)


def test_range_condition_within_bounds() -> None:
    """Test range condition with value within bounds."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "20")
    assert validator.is_valid(state)


def test_range_condition_below_min() -> None:
    """Test range condition with value below minimum."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "5")
    assert not validator.is_valid(state)


def test_range_condition_above_max() -> None:
    """Test range condition with value above maximum."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "35")
    assert not validator.is_valid(state)


def test_range_condition_only_min() -> None:
    """Test range condition with only minimum value."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
        }
    ]
    validator = ConditionValidator(conditions)

    state_valid = State("sensor.test", "15")
    assert validator.is_valid(state_valid)

    state_invalid = State("sensor.test", "5")
    assert not validator.is_valid(state_invalid)


def test_range_condition_only_max() -> None:
    """Test range condition with only maximum value."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MAX: 30,
        }
    ]
    validator = ConditionValidator(conditions)

    state_valid = State("sensor.test", "25")
    assert validator.is_valid(state_valid)

    state_invalid = State("sensor.test", "35")
    assert not validator.is_valid(state_invalid)


def test_range_condition_non_numeric() -> None:
    """Test range condition with non-numeric value."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "not_a_number")
    assert not validator.is_valid(state)


def test_regex_condition_matches() -> None:
    """Test regex condition with matching pattern."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"^(on|off)$",
        }
    ]
    validator = ConditionValidator(conditions)

    state_on = State("sensor.test", "on")
    assert validator.is_valid(state_on)

    state_off = State("sensor.test", "off")
    assert validator.is_valid(state_off)


def test_regex_condition_no_match() -> None:
    """Test regex condition with non-matching pattern."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"^(on|off)$",
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "invalid")
    assert not validator.is_valid(state)


def test_regex_condition_numeric_pattern() -> None:
    """Test regex condition with numeric pattern."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"^\d+\.\d{2}$",  # Two decimal places
        }
    ]
    validator = ConditionValidator(conditions)

    state_valid = State("sensor.test", "12.34")
    assert validator.is_valid(state_valid)

    state_invalid = State("sensor.test", "12.3")
    assert not validator.is_valid(state_invalid)


def test_multiple_conditions_all_pass() -> None:
    """Test multiple conditions where all pass."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        },
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"^\d+$",
        },
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "20")
    assert validator.is_valid(state)


def test_multiple_conditions_one_fails() -> None:
    """Test multiple conditions where one fails."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_RANGE,
            CONF_CONDITION_MIN: 10,
            CONF_CONDITION_MAX: 30,
        },
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"^\d+$",
        },
    ]
    validator = ConditionValidator(conditions)

    # Value 5 is outside range but matches regex
    state = State("sensor.test", "5")
    assert not validator.is_valid(state)

    # Value 20.5 is within range but doesn't match regex
    state2 = State("sensor.test", "20.5")
    assert not validator.is_valid(state2)


def test_invalid_regex_pattern() -> None:
    """Test handling of invalid regex pattern."""
    conditions = [
        {
            CONF_CONDITION_TYPE: CONDITION_TYPE_REGEX,
            CONF_CONDITION_PATTERN: r"[invalid(regex",
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "test")
    # Invalid pattern should return False
    assert not validator.is_valid(state)


def test_unknown_condition_type() -> None:
    """Test handling of unknown condition type."""
    conditions = [
        {
            CONF_CONDITION_TYPE: "unknown_type",
        }
    ]
    validator = ConditionValidator(conditions)
    state = State("sensor.test", "test")
    # Unknown condition type should be ignored (return True)
    assert validator.is_valid(state)
