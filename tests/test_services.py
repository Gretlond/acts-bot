import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import act_service
import db
import registry_service
from act_service import create_act_with_file, update_act_with_file
from generate_act import build_act
from registry_service import archive_acts, merge_acts_to_docx, rename_act_files
from utils import build_template_data, parse_date


def _template_data(number="201"):
    obj = {
        "name": "Тестовый объект",
        "gen_person_post": "Директор",
        "gen_contractor": "ООО Тест",
        "gen_person": "Иванов И.И.",
        "gen_short": "Иванов",
        "tech_post": "Инженер",
        "tech_place": "ООО Тест",
        "tech_name": "Петров П.П.",
        "tech_short": "Петров",
        "project_firm": "Проект",
        "project_date": "01.01.2026",
    }
    start = parse_date("01.10.2026")
    end = parse_date("05.10.2026")
    return build_template_data(
        obj,
        "Бетонирование днища позиция №33",
        "1-2",
        "КЖ-1",
        start,
        end,
        end,
        "Бетон B25",
        number,
    )


class ActServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(db, "DB_PATH", self.root / "acts.db")
        self.patch.start()
        db.init_db()
        with db.db_conn() as conn:
            conn.execute("INSERT INTO objects (name) VALUES ('Объект')")
            self.object_id = conn.execute("SELECT id FROM objects LIMIT 1").fetchone()["id"]

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def _save_kwargs(self, number="201"):
        return dict(
            object_id=self.object_id,
            position_id=None,
            act_number=number,
            act_date="05.10.2026 г.",
            start_date="01.10.2026 г.",
            end_date="05.10.2026 г.",
            work_full="Бетонирование днища позиция №33",
            sheets="1-2",
            section="КЖ",
            cipher="КЖ-1",
            work_type_name="Бетонирование",
            work_name="днища",
            position_number="33",
            materials_data="[]",
            status="ready",
        )

    def test_file_and_row_are_created(self):
        target = self.root / "acts" / "act.docx"
        path, act_id = create_act_with_file(_template_data(), target, **self._save_kwargs())
        self.assertTrue(path.exists())
        act = db.get_act(act_id)
        self.assertIsNotNone(act)
        self.assertTrue(path.name in act["file_path"] or path.exists())

    def test_duplicate_rolls_back_new_file(self):
        target_one = self.root / "acts" / "one.docx"
        create_act_with_file(_template_data(), target_one, **self._save_kwargs("201"))
        target_two = self.root / "acts" / "two.docx"
        with self.assertRaises(db.DuplicateActNumberError):
            create_act_with_file(_template_data(), target_two, **self._save_kwargs("201"))
        self.assertFalse(target_two.exists())

    def test_update_rebuilds_file_and_row(self):
        target_one = self.root / "acts" / "one.docx"
        _, act_id = create_act_with_file(
            _template_data("201"), target_one, **self._save_kwargs("201")
        )
        target_two = self.root / "acts" / "two.docx"
        with patch.object(act_service, "archive_old_act_file", return_value=None):
            updated = update_act_with_file(
                act_id,
                _template_data("202"),
                target_two,
                target_one,
                **self._save_kwargs("202"),
            )
        self.assertEqual(updated, target_two)
        self.assertTrue(target_two.exists())
        act = db.get_act(act_id)
        self.assertEqual(act["act_number"], "202")
        self.assertEqual(Path(act["file_path"]), target_two)

    def test_update_rolls_back_on_duplicate_number(self):
        target_one = self.root / "acts" / "one.docx"
        create_act_with_file(_template_data("201"), target_one, **self._save_kwargs("201"))
        target_two = self.root / "acts" / "two.docx"
        _, second_id = create_act_with_file(
            _template_data("202"), target_two, **self._save_kwargs("202")
        )
        target_three = self.root / "acts" / "three.docx"
        with self.assertRaises(db.DuplicateActNumberError):
            update_act_with_file(
                second_id,
                _template_data("201"),
                target_three,
                target_two,
                **self._save_kwargs("201"),
            )
        self.assertFalse(target_three.exists())
        self.assertTrue(target_two.exists())
        self.assertEqual(db.get_act(second_id)["act_number"], "202")

    def test_rename_files_updates_database(self):
        acts_dir = self.root / "acts"
        acts_dir.mkdir()
        old = acts_dir / "old-name.docx"
        old.write_bytes(b"old")
        act_id = db.save_act(
            object_id=self.object_id,
            position_id=None,
            act_number="777",
            act_date="05.10.2026 г.",
            start_date="01.10.2026 г.",
            end_date="05.10.2026 г.",
            work_full="Бетонирование днища позиция №33",
            file_path=str(old),
            work_type_name="Бетонирование",
            work_name="днища",
            position_number="33",
            status="ready",
        )
        with patch.object(registry_service, "ACTS_DIR", acts_dir):
            renamed, skipped = rename_act_files(db.get_acts_for_object(self.object_id))
        self.assertEqual((renamed, skipped), (1, 0))
        act = db.get_act(act_id)
        new_path = Path(act["file_path"])
        self.assertTrue(new_path.exists())
        self.assertFalse(old.exists())
        self.assertEqual(new_path.name, "АКТ №777 Бетонирование поз. №33.docx")

    def test_rename_archived_file_stays_in_archive(self):
        archive_dir = self.root / "archive"
        year_dir = archive_dir / "2026"
        year_dir.mkdir(parents=True)
        old = year_dir / "old-name.docx"
        old.write_bytes(b"old")
        act_id = db.save_act(
            object_id=self.object_id,
            position_id=None,
            act_number="779",
            act_date="05.10.2026 г.",
            start_date="01.10.2026 г.",
            end_date="05.10.2026 г.",
            work_full="Бетонирование днища позиция №33",
            file_path=str(old),
            work_type_name="Бетонирование",
            work_name="днища",
            position_number="33",
            status="archived",
        )
        with (
            patch.object(registry_service, "ACTS_DIR", self.root / "acts"),
            patch.object(registry_service, "ARCHIVE_DIR", archive_dir),
        ):
            renamed, skipped = rename_act_files([db.get_act(act_id)])
        self.assertEqual((renamed, skipped), (1, 0))
        new_path = Path(db.get_act(act_id)["file_path"])
        self.assertEqual(new_path.parent, year_dir)
        self.assertTrue(new_path.exists())

    def test_archive_changes_status(self):
        act_id = db.save_act(
            object_id=self.object_id,
            position_id=None,
            act_number="778",
            act_date="05.10.2025 г.",
            start_date="01.10.2025 г.",
            end_date="05.10.2025 г.",
            work_full="Бетонирование днища позиция №33",
            file_path="acts/missing.docx",
            status="ready",
        )
        with patch.object(registry_service, "archive_act_to_archive", return_value=None):
            archived, failed = archive_acts([db.get_act(act_id)])
        self.assertEqual((archived, failed), (1, 0))
        self.assertEqual(db.get_act(act_id)["status"], "archived")

    def test_merge_two_docx(self):
        first = self.root / "first.docx"
        second = self.root / "second.docx"
        build_act(_template_data("201"), out_path=first)
        build_act(_template_data("202"), out_path=second)
        target = self.root / "package.docx"
        merge_acts_to_docx([{"file_path": str(first)}, {"file_path": str(second)}], target)
        self.assertTrue(target.exists())
        self.assertGreater(target.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
