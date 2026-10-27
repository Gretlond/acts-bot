import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from fsm_storage import SQLiteStorage
from registry_service import acts_to_csv, acts_to_xlsx, search_acts


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.patch = patch.object(db, "DB_PATH", self.db_path)
        self.patch.start()
        db.init_db()
        with db.db_conn() as conn:
            conn.execute("INSERT INTO objects (name) VALUES ('Тестовый объект')")
            self.object_id = conn.execute("SELECT id FROM objects LIMIT 1").fetchone()["id"]

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def _save(self, number, status="ready", date="05.10.2026 г."):
        return db.save_act(
            object_id=self.object_id,
            position_id=None,
            act_number=number,
            act_date=date,
            start_date="01.10.2026 г.",
            end_date=date,
            work_full="Бетонирование днища позиция №33",
            file_path=f"acts/act-{number}.docx",
            work_type_name="Бетонирование",
            work_name="днища",
            position_number="33",
            materials_data='[{"id": 1, "name": "Бетон B25", "cert": "паспорт №1"}]',
            status=status,
        )

    def test_ready_act_number_is_unique(self):
        self._save("103")
        with self.assertRaises(db.DuplicateActNumberError):
            self._save("103")
        self.assertTrue(db.act_number_exists(self.object_id, "103"))

    def test_draft_is_not_blocked_by_ready_act(self):
        self._save("103")
        draft_id = db.save_draft_act(self.object_id, "103", "preview", "{}")
        self.assertIsNotNone(draft_id)

    def test_draft_can_be_found_and_deleted(self):
        draft_id = db.save_draft_act(self.object_id, "104", "preview", '{"work_name": "стены"}')
        draft = db.get_act(draft_id)
        self.assertEqual(draft["status"], "draft")
        db.delete_act(draft_id)
        self.assertIsNone(db.get_act(draft_id))

    def test_find_duplicate_and_search(self):
        self._save("103")
        duplicate = db.find_duplicate_act(
            self.object_id,
            "Бетонирование",
            "днища",
            "33",
            "01.10.2026 г.",
            "05.10.2026 г.",
        )
        self.assertEqual(duplicate["act_number"], "103")
        materials = '[{"id": 1, "name": "Бетон B25", "cert": "паспорт №1"}]'
        exact = db.find_duplicate_act(
            self.object_id,
            "Бетонирование",
            "днища",
            "33",
            "01.10.2026 г.",
            "05.10.2026 г.",
            work_full="Бетонирование днища позиция №33",
            materials_json=materials,
        )
        self.assertEqual(exact["act_number"], "103")
        self.assertIsNone(
            db.find_duplicate_act(
                self.object_id,
                "Бетонирование",
                "днища",
                "33",
                "01.10.2026 г.",
                "05.10.2026 г.",
                work_full="Другая работа",
                materials_json=materials,
            )
        )
        self.assertIsNone(
            db.find_duplicate_act(
                self.object_id,
                "Бетонирование",
                "днища",
                "33",
                "01.10.2026 г.",
                "05.10.2026 г.",
                work_full="Бетонирование днища позиция №33",
                materials_json='[{"id": 2, "name": "Бетон B30", "cert": ""}]',
            )
        )
        self.assertEqual(len(search_acts(self.object_id, "за октябрь")), 1)
        self.assertEqual(len(search_acts(self.object_id, "позиция 33")), 1)
        self.assertEqual(len(search_acts(self.object_id, "Бетон B25")), 1)
        self.assertEqual(len(search_acts(self.object_id, "103")), 1)
        self.assertEqual(len(search_acts(self.object_id, "акт №103")), 1)
        self.assertEqual(len(search_acts(self.object_id, "2026")), 1)
        self.assertEqual(len(search_acts(self.object_id, "05.10.2026")), 1)
        self.assertEqual(len(search_acts(self.object_id, "06.10.2026")), 0)
        self.assertEqual(len(search_acts(self.object_id, "ноябрь")), 0)

    def test_acts_before_date(self):
        self._save("101", date="01.09.2026 г.")
        self._save("102", date="01.11.2026 г.")
        acts = db.get_acts_before_date(self.object_id, "01.10.2026")
        self.assertEqual([a["act_number"] for a in acts], ["101"])

    def test_acts_in_period(self):
        self._save("101", date="01.09.2026 г.")
        self._save("102", date="01.11.2026 г.")
        self._save("103", date="15.10.2026 г.")
        acts = db.get_acts_in_period(self.object_id, "01.10.2026", "31.10.2026")
        self.assertEqual([a["act_number"] for a in acts], ["103"])
        self.assertEqual(db.get_acts_in_period(self.object_id, "31.10.2026", "01.10.2026"), [])
        self.assertEqual(db.get_acts_in_period(self.object_id, "мусор", None), [])

    def test_status_counts_include_archive(self):
        self._save("105", status="archived")
        counts = db.get_act_status_counts(self.object_id)
        self.assertEqual(counts["archived"], 1)

    def test_csv_export(self):
        self._save("103")
        target = Path(self.temp.name) / "acts.csv"
        acts_to_csv(db.get_acts_for_object(self.object_id), target)
        text = target.read_text(encoding="utf-8-sig")
        self.assertIn("№ акта", text)
        self.assertIn("103", text)
        self.assertIn("Бетон B25", text)

    def test_xlsx_export(self):
        from openpyxl import load_workbook

        self._save("103")
        target = Path(self.temp.name) / "acts.xlsx"
        acts_to_xlsx(db.get_acts_for_object(self.object_id), target)
        workbook = load_workbook(target)
        sheet = workbook.active
        self.assertEqual(sheet["A1"].value, "№ акта")
        self.assertEqual(sheet["A2"].value, "103")
        self.assertEqual(sheet.auto_filter.ref, "A1:M2")


class FSMStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "fsm.db"
        self.patch = patch.object(db, "DB_PATH", self.db_path)
        self.patch.start()
        db.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_state_and_data_survive_new_storage_instance(self):
        from aiogram.fsm.storage.base import StorageKey

        key = StorageKey(bot_id=1, chat_id=2, user_id=3)

        async def scenario():
            storage = SQLiteStorage()
            await storage.set_state(key, "NewAct:entering_act_number")
            await storage.set_data(key, {"act_number": "103"})
            fresh = SQLiteStorage()
            state = await fresh.get_state(key)
            data = await fresh.get_data(key)
            return state, data

        state, data = asyncio.run(scenario())
        self.assertEqual(state, "NewAct:entering_act_number")
        self.assertEqual(data["act_number"], "103")

    def test_schema_is_idempotent(self):
        db.init_db()
        conn = sqlite3.connect(self.db_path)
        try:
            indexes = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        self.assertIn("idx_acts_object_number_unique", indexes)


if __name__ == "__main__":
    unittest.main()
