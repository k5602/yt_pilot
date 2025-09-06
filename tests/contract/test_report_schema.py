import json
from pathlib import Path
import pytest

SCHEMA_PATH = Path("specs/001-refactor-app-into/contracts/report-schema.json")


@pytest.mark.contract
def test_report_schema_basic_fields():
    data = json.loads(SCHEMA_PATH.read_text())
    # Required top-level keys
    for key in ["$schema", "$id", "title", "type", "required", "properties"]:
        assert key in data
    assert "schemaVersion" in data["properties"]
    pattern = data["properties"]["schemaVersion"].get("pattern")
    assert pattern == r"^1\.0\.0$"
    assert "videos" in data["properties"]


@pytest.mark.contract
def test_report_schema_required_arrays():
    data = json.loads(SCHEMA_PATH.read_text())
    req = set(data["required"])  # should include core identity fields
    for field in [
        "schemaVersion",
        "playlistUrl",
        "started",
        "ended",
        "counts",
        "videos",
    ]:
        assert field in req
