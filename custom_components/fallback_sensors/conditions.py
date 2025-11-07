"""Condition validation for Fallback Sensors."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import State

from .const import (
    CONDITION_TYPE_RANGE,
    CONDITION_TYPE_REGEX,
    CONF_CONDITION_MAX,
    CONF_CONDITION_MIN,
    CONF_CONDITION_PATTERN,
    CONF_CONDITION_TYPE,
)

_LOGGER = logging.getLogger(__name__)


class ConditionValidator:
    """Validates entity states against custom conditions."""

    def __init__(self, conditions: list[dict[str, Any]] | None = None) -> None:
        """Initialize the condition validator.

        Args:
            conditions: List of condition dictionaries.
        """
        self._conditions = conditions or []
        self._compiled_patterns: dict[str, re.Pattern] = {}

        # Pre-compile regex patterns for performance
        for condition in self._conditions:
            if condition.get(CONF_CONDITION_TYPE) == CONDITION_TYPE_REGEX:
                pattern = condition.get(CONF_CONDITION_PATTERN)
                if pattern:
                    try:
                        self._compiled_patterns[pattern] = re.compile(pattern)
                    except re.error as err:
                        _LOGGER.error(
                            "Invalid regex pattern '%s': %s",
                            pattern,
                            err,
                        )

    def is_valid(self, state: State) -> bool:
        """Check if a state is valid according to conditions.

        Args:
            state: Entity state to validate.

        Returns:
            True if state passes all conditions, False otherwise.
        """
        if not self._conditions:
            # No conditions means always valid
            return True

        for condition in self._conditions:
            if not self._check_condition(state, condition):
                return False

        return True

    def _check_condition(self, state: State, condition: dict[str, Any]) -> bool:
        """Check a single condition against a state.

        Args:
            state: Entity state to check.
            condition: Condition dictionary.

        Returns:
            True if condition passes, False otherwise.
        """
        condition_type = condition.get(CONF_CONDITION_TYPE)

        if condition_type == CONDITION_TYPE_RANGE:
            return self._check_range_condition(state, condition)
        elif condition_type == CONDITION_TYPE_REGEX:
            return self._check_regex_condition(state, condition)
        else:
            _LOGGER.warning("Unknown condition type: %s", condition_type)
            return True

    def _check_range_condition(
        self, state: State, condition: dict[str, Any]
    ) -> bool:
        """Check if state value is within a numeric range.

        Args:
            state: Entity state to check.
            condition: Range condition dictionary.

        Returns:
            True if value is within range, False otherwise.
        """
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Cannot convert state '%s' to number for range check",
                state.state,
            )
            return False

        min_value = condition.get(CONF_CONDITION_MIN)
        max_value = condition.get(CONF_CONDITION_MAX)

        if min_value is not None and value < min_value:
            _LOGGER.debug(
                "Value %s is below minimum %s",
                value,
                min_value,
            )
            return False

        if max_value is not None and value > max_value:
            _LOGGER.debug(
                "Value %s is above maximum %s",
                value,
                max_value,
            )
            return False

        return True

    def _check_regex_condition(
        self, state: State, condition: dict[str, Any]
    ) -> bool:
        """Check if state value matches a regex pattern.

        Args:
            state: Entity state to check.
            condition: Regex condition dictionary.

        Returns:
            True if value matches pattern, False otherwise.
        """
        pattern = condition.get(CONF_CONDITION_PATTERN)
        if not pattern:
            return True

        compiled_pattern = self._compiled_patterns.get(pattern)
        if not compiled_pattern:
            # Pattern compilation failed during init
            return False

        state_str = str(state.state)
        matches = bool(compiled_pattern.match(state_str))

        if not matches:
            _LOGGER.debug(
                "State '%s' does not match pattern '%s'",
                state_str,
                pattern,
            )

        return matches
