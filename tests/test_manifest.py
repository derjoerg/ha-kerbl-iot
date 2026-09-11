"""Static sanity checks on manifest.json that don't need a running hass."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.kerbl_iot.const import DOMAIN

MANIFEST_PATH = (
    Path(__file__).parent.parent / "custom_components" / "kerbl_iot" / "manifest.json"
)


def test_manifest_matches_domain_constant() -> None:
    """The manifest domain must always match const.DOMAIN."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "hub"
    assert manifest["iot_class"] == "cloud_push"
    assert manifest["requirements"] == ["kerbl-iot==0.1.5"]
    assert all(owner.startswith("@") for owner in manifest["codeowners"])
