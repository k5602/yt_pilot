import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
import pytest

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def temp_output_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture()
def sample_manifest_entry():
    return {
        "status": "success",
        "quality": "720p",
        "fallback": False,
        "retries": 0,
        "filename": "000-sample.mp4",
    }
