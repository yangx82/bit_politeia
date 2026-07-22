"""
Agent Data & Identity Migration Unit Tests
===========================================
"""

import os
import sys
import tempfile
import zipfile
import pytest
from pathlib import Path

# Ensure we can import from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from scripts.export_agent_data import export_data, calculate_file_hash
from scripts.import_agent_data import import_data


def test_export_and_import_cycle():
    """
    Test a full export and import cycle to verify data integrity and manifest generation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip = os.path.join(tmp_dir, "test_backup.zip")

        # 1. Execute Export
        exported_path = export_data(output_path=tmp_zip, include_logs=False)
        assert os.path.exists(exported_path)
        assert os.path.getsize(exported_path) > 0

        # Check Zip Contents
        with zipfile.ZipFile(exported_path, "r") as zipf:
            namelist = zipf.namelist()
            assert "export_manifest.json" in namelist
            assert "frontend_state_backup.json" in namelist

        # 2. Checksum calculation
        checksum = calculate_file_hash(exported_path)
        assert len(checksum) == 64  # SHA256 length

        # 3. Execute Import Simulation with Checksum Verification
        success = import_data(input_path=exported_path, checksum=checksum)
        assert success is True

        # Check generated frontend restore helper HTML
        helper_path = Path(project_root) / "frontend_restore_helper.html"
        assert helper_path.exists()
