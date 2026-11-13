import unittest
from unittest.mock import patch

from backend.parser_health_probe import check_parser


class ParserHealthProbeTests(unittest.TestCase):
    def test_valid_synthetic_school_search(self):
        school = {"id": "1234:대전예시학교", "name": "대전예시학교", "region": "대전"}
        with patch("backend.parser_health_probe.search_schools", return_value=[school]) as search:
            self.assertEqual(check_parser(), 1)
            search.assert_called_once_with("대전")

    def test_empty_or_malformed_results_fail_closed(self):
        for value in ([], None, {},
                      [{"id": "bad", "name": "학교", "region": "대전"}],
                      [{"id": "1234:학교", "name": "", "region": "대전"}],
                      [{"id": "1234:학교", "name": "학교"}]):
            with self.subTest(value=value):
                with patch("backend.parser_health_probe.search_schools", return_value=value):
                    with self.assertRaises(RuntimeError):
                        check_parser()


if __name__ == "__main__":
    unittest.main()
