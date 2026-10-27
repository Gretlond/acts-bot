import unittest

from utils import (
    act_filename,
    cert_label,
    compose_full_work,
    date_range_is_valid,
    parse_date,
    parse_dates_range,
)


class ActFilenameTests(unittest.TestCase):
    def test_basic_name(self):
        self.assertEqual(
            act_filename("103", "Бетонирование", "днища", "33"),
            "АКТ №103 Бетонирование поз. №33.docx",
        )

    def test_position_range(self):
        self.assertEqual(
            act_filename("104", "Армирование", "", "21-28"),
            "АКТ №104 Армирование поз. №21-28.docx",
        )

    def test_work_name_fallback(self):
        self.assertEqual(
            act_filename("105", "", "монолитных стен", ""),
            "АКТ №105 монолитных стен.docx",
        )

    def test_invalid_windows_chars(self):
        self.assertEqual(
            act_filename("106/1", "Монтаж: металл", "", "33"),
            "АКТ №106_1 Монтаж_ металл поз. №33.docx",
        )

    def test_empty_number(self):
        self.assertEqual(act_filename("", "Монтаж", "", ""), "АКТ №б_н Монтаж.docx")


class DateTests(unittest.TestCase):
    def test_parse_date(self):
        value = parse_date("05.10.2026")
        self.assertEqual(value["full"], "05.10.2026 г.")
        self.assertEqual(value["month_name"], "октября")

    def test_parse_date_with_suffix(self):
        self.assertEqual(parse_date("5.10.2026 г.")["day"], "05")

    def test_invalid_calendar_date(self):
        with self.assertRaises(ValueError):
            parse_date("31.02.2026")

    def test_dates_range(self):
        start, end = parse_dates_range("01.10.2026 - 15.10.2026")
        self.assertEqual(start["full"], "01.10.2026 г.")
        self.assertEqual(end["full"], "15.10.2026 г.")

    def test_range_order(self):
        start = parse_date("01.10.2026")
        end = parse_date("02.10.2026")
        self.assertTrue(date_range_is_valid(start, end))
        self.assertFalse(date_range_is_valid(end, start))


class OtherUtilsTests(unittest.TestCase):
    def test_compose_full_work(self):
        self.assertEqual(
            compose_full_work("Бетонирование", "днища", "33"),
            "Бетонирование днища позиция №33",
        )

    def test_cert_label(self):
        cert = {
            "number": "123",
            "doc_type": "passport_quality",
            "date_from": "01.09.2026",
        }
        self.assertEqual(
            cert_label(cert),
            "паспорт качества №123 от 01.09.2026",
        )


if __name__ == "__main__":
    unittest.main()
