"""Guard rails on the user facing strings."""

from __future__ import annotations

import json
from pathlib import Path

COMPONENT = Path("custom_components/fallback_sensors")
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations"


def test_english_translation_matches_strings() -> None:
    """`translations/en.json` is what Home Assistant actually displays.

    `strings.json` alone is never read for a custom integration, so the two
    files must not drift apart.
    """
    assert json.loads(STRINGS.read_text()) == json.loads(
        (TRANSLATIONS / "en.json").read_text()
    )


def test_every_form_field_has_a_label() -> None:
    """Every field of every step is labelled in the translations."""
    from custom_components.fallback_sensors.config_flow import (
        _async_build_schema,
    )

    strings = json.loads(STRINGS.read_text())

    for flow, include_unique_id, step in (
        ("config", True, "user"),
        ("options", False, "init"),
    ):
        labels = strings[flow]["step"][step]["data"]
        schema = _async_build_schema({}, include_unique_id=include_unique_id)
        for marker in schema.schema:
            assert str(marker) in labels, f"{flow}.{step}: {marker} has no label"
