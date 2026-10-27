import unittest

from utils import act_filename


class ActFilenameTests(unittest.TestCase):
    def test_basic_name(self):
        self.assertEqual(
            act_filename("103", "Бетонирование", "днища", "33"),
            "АКТ№103 (Бетонирование) поз. №33.docx",
        )

    def test_position_range(self):
        self.assertEqual(
            act_filename("104", "Армирование", "", "21-28"),
            "АКТ№104 (Армирование) поз. №21-28.docx",
        )

    def test_work_name_fallback(self):
        self.assertEqual(
            act_filename("105", "", "монолитных стен", ""),
            "АКТ№105 (монолитных стен).docx",
        )

    def test_invalid_windows_chars(self):
        self.assertEqual(
            act_filename("106/1", "Монтаж: металл", "", "33"),
            "АКТ№106_1 (Монтаж_ металл) поз. №33.docx",
        )

    def test_empty_number(self):
        self.assertEqual(act_filename("", "Монтаж", "", ""),
                         "АКТ№б_н (Монтаж).docx")


if __name__ == "__main__":
    unittest.main()
