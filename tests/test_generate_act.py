import tempfile
import unittest
import zipfile
from pathlib import Path

from generate_act import build_act
from utils import build_template_data, parse_date


class GenerateActTests(unittest.TestCase):
    def test_build_act_from_real_template(self):
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
        data = build_template_data(
            obj,
            "Бетонирование днища позиция №33",
            "1-2",
            "КЖ-1",
            start,
            end,
            end,
            "Бетон B25 (паспорт качества №1)",
            "103",
        )
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "act.docx"
            result = build_act(data, out_path=target)
            self.assertTrue(result.exists())
            self.assertTrue(zipfile.is_zipfile(result))
            self.assertGreater(result.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
