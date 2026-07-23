"""
Agent Data & Identity Migration Unit Tests
===========================================
"""

import os
import sys
import tempfile
import zipfile
import unittest
from pathlib import Path

# Ensure we can import from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from scripts.export_agent_data import export_data, calculate_file_hash
from scripts.import_agent_data import import_data


class TestMigration(unittest.TestCase):
    def test_export_and_import_cycle(self):
        """
        Test a full export and import cycle to verify data integrity and manifest generation.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = os.path.join(tmp_dir, "test_backup.zip")

            # 1. Execute Export
            exported_path = export_data(output_path=tmp_zip, include_logs=False)
            self.assertTrue(os.path.exists(exported_path))
            self.assertGreater(os.path.getsize(exported_path), 0)

            # Check Zip Contents
            with zipfile.ZipFile(exported_path, "r") as zipf:
                namelist = zipf.namelist()
                self.assertIn("export_manifest.json", namelist)
                self.assertIn("frontend_state_backup.json", namelist)

            # 2. Checksum calculation
            checksum = calculate_file_hash(exported_path)
            self.assertEqual(len(checksum), 64)  # SHA256 length

            # 3. Execute Import Simulation with Checksum Verification
            success = import_data(input_path=exported_path, checksum=checksum)
            self.assertTrue(success)

            # Check generated frontend restore helper HTML
            helper_path = Path(project_root) / "frontend_restore_helper.html"
            self.assertTrue(helper_path.exists())
