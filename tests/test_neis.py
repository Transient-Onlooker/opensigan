import json
import unittest
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from backend.neis import (
    Meal,
    NEISAPIError,
    NEISClient,
    NEISNetworkError,
    NEISResponseError,
    School,
)


def response(endpoint, rows, count=None):
    return json.dumps({endpoint: [
        {"head": [{"list_total_count": len(rows) if count is None else count},
                  {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]},
        {"row": rows},
    ]}, ensure_ascii=False).encode("utf-8")


class NEISTests(unittest.TestCase):
    def test_school_candidates_preserve_duplicate_names_and_codes(self):
        rows = [
            {"ATPT_OFCDC_SC_CODE": "A10", "SD_SCHUL_CODE": "1000001", "SCHUL_NM": "가람고등학교", "ORG_RDNMA": "서울"},
            {"ATPT_OFCDC_SC_CODE": "B10", "SD_SCHUL_CODE": "2000001", "SCHUL_NM": "가람고등학교", "ORG_RDNMA": "부산"},
        ]
        calls = []

        def transport(url, timeout):
            calls.append((url, timeout))
            return response("schoolInfo", rows)

        client = NEISClient.from_environment(environ={"NEIS_API_KEY": "test-key"}, transport=transport)
        candidates = client.search_schools("가람고등학교")
        self.assertEqual([(s.office_code, s.school_code, s.address) for s in candidates],
                         [("A10", "1000001", "서울"), ("B10", "2000001", "부산")])
        query = parse_qs(urlsplit(calls[0][0]).query)
        self.assertEqual(query["SCHUL_NM"], ["가람고등학교"])
        self.assertEqual(query["KEY"], ["test-key"])
        self.assertEqual(calls[0][1], 8.0)
        self.assertNotIn("test-key", repr(candidates))

    def test_meals_are_normalized_and_include_allergy_markers(self):
        seen = []

        def transport(url, timeout):
            seen.append(parse_qs(urlsplit(url).query))
            return response("mealServiceDietInfo", [{"MLSV_YMD": "20261110", "MMEAL_SC_NM": "중식",
                "DDISH_NM": "밥<br/>계란(1.5.)", "CAL_INFO": "700 Kcal", "ORPLC_INFO": "쌀: 국내산"}])

        client = NEISClient("key", transport=transport)
        meals = client.get_meals(School("A10", "1000001", "학교"), date(2026, 11, 10), date(2026, 11, 11))
        self.assertEqual(meals, [Meal("2026-11-10", "중식", "밥<br/>계란(1.5.)", "700 Kcal", "쌀: 국내산")])
        self.assertEqual(seen[0]["ATPT_OFCDC_SC_CODE"], ["A10"])
        self.assertEqual(seen[0]["SD_SCHUL_CODE"], ["1000001"])
        self.assertEqual(seen[0]["MLSV_TO_YMD"], ["20261111"])

    def test_no_data_for_schools_and_meals(self):
        empty = json.dumps({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}})
        client = NEISClient("key", transport=lambda url, timeout: empty)
        self.assertEqual(client.search_schools("없는 학교"), [])
        self.assertEqual(client.get_meals(School("A10", "1", "학교"), date(2026, 1, 1), date(2026, 1, 1)), [])

    def test_pagination_returns_all_candidates(self):
        def transport(url, timeout):
            page = parse_qs(urlsplit(url).query)["pIndex"][0]
            row = {"ATPT_OFCDC_SC_CODE": "A10", "SD_SCHUL_CODE": page, "SCHUL_NM": "학교"}
            return response("schoolInfo", [row], count=2)
        candidates = NEISClient("key", transport=transport).search_schools("학교", office_code="A10")
        self.assertEqual([s.school_code for s in candidates], ["1", "2"])

    def test_api_error_is_distinct_from_empty_data(self):
        for data in [
            {"RESULT": {"CODE": "ERROR-290", "MESSAGE": "invalid key"}},
            {"schoolInfo": [{"head": [{"RESULT": {"CODE": "ERROR-300"}}]}]},
        ]:
            with self.subTest(data=data):
                client = NEISClient("secret", transport=lambda url, timeout: json.dumps(data))
                with self.assertRaises(NEISAPIError) as error:
                    client.search_schools("학교")
                self.assertNotIn("secret", str(error.exception))

    def test_network_errors_are_distinct_and_hide_request_url(self):
        for error in [URLError("https://example.test/?KEY=secret"), TimeoutError(),
                      HTTPError("https://example.test/?KEY=secret", 429, "error", None, None)]:
            with self.subTest(error=type(error).__name__):
                def transport(url, timeout):
                    raise error
                with self.assertRaises(NEISNetworkError) as caught:
                    NEISClient("secret", transport=transport).search_schools("학교")
                self.assertNotIn("secret", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_malformed_response_is_not_empty(self):
        payloads = [b"not json", b"[]", b"{}", response("schoolInfo", [{}]),
                    response("schoolInfo", [], count=2)]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(NEISResponseError):
                    NEISClient("key", transport=lambda url, timeout: payload).search_schools("학교")

    def test_invalid_inputs_fail_without_network(self):
        with self.assertRaises(ValueError):
            NEISClient.from_environment(environ={})
        client = NEISClient("key", transport=lambda url, timeout: self.fail("unexpected request"))
        with self.assertRaises(ValueError):
            client.search_schools("  ")
        with self.assertRaises(ValueError):
            client.get_meals(School("", "1", "학교"), date(2026, 1, 1), date(2026, 1, 1))
        with self.assertRaises(ValueError):
            client.get_meals(School("A10", "1", "학교"), date(2026, 1, 2), date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
