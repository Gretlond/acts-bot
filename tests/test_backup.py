import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import backup
import db


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "acts.db"
        self.backups = self.root / "backups"
        self.acts = self.root / "acts"
        self.certs = self.root / "certificates"
        self.acts.mkdir()
        self.certs.mkdir()
        self.patches = [
            patch.object(db, "DB_PATH", self.db_path),
            patch.object(backup, "DB_PATH", self.db_path),
            patch.object(backup, "BACKUPS_DIR", self.backups),
            patch.object(backup, "ACTS_DIR", self.acts),
            patch.object(backup, "CERTIFICATES_DIR", self.certs),
        ]
        for item in self.patches:
            item.start()
        db.init_db()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_database_backup_is_valid(self):
        target = backup.backup_database("test")
        self.assertIsNotNone(target)
        self.assertTrue(target.exists())
        conn = sqlite3.connect(target)
        try:
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        self.assertIn("acts", tables)
        self.assertFalse(list(self.backups.glob("*.tmp")))

    def test_files_backup_contains_act(self):
        (self.acts / "Akt.docx").write_bytes(b"docx")
        target = backup.backup_files("test")
        self.assertIsNotNone(target)
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
        self.assertIn("acts/Akt.docx", names)


if __name__ == "__main__":
    unittest.main()
