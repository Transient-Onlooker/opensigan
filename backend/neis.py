"""Server-side NEIS school search and meal client.

School search supplies candidates only; it does not match a Comcigan school.
The caller must confirm and retain the NEIS office and school code pair.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


class NEISError(Exception):
    pass


class NEISNetworkError(NEISError):
    """A connection, timeout, or HTTP error occurred."""


class NEISAPIError(NEISError):
    """NEIS rejected the request."""


class NEISResponseError(NEISError):
    """The NEIS response is malformed or incomplete."""


@dataclass(frozen=True)
class School:
    office_code: str
    school_code: str
    name: str
    kind: str | None = None
    address: str | None = None


@dataclass(frozen=True)
class Meal:
    date: str
    meal_type: str
    menu: str
    calories: str | None = None
    origin: str | None = None


def _transport(url: str, timeout: float) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


class NEISClient:
    """Keep this client and its key on the server, never in a browser bundle."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 8.0,
        transport: Callable[[str, float], bytes | str] | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("NEIS_API_KEY가 설정되지 않았습니다.")
        if timeout <= 0:
            raise ValueError("timeout은 0보다 커야 합니다.")
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._transport = transport or _transport

    @classmethod
    def from_environment(
        cls, *, environ: Mapping[str, str] | None = None, **kwargs: Any
    ) -> "NEISClient":
        source = os.environ if environ is None else environ
        return cls(source.get("NEIS_API_KEY", ""), **kwargs)

    def _request(self, endpoint: str, params: Mapping[str, str]) -> tuple[list[dict], int]:
        query = urlencode({"KEY": self._api_key, "Type": "json", **params})
        url = f"https://open.neis.go.kr/hub/{endpoint}?{query}"
        try:
            raw = self._transport(url, self._timeout)
        except HTTPError as exc:
            raise NEISNetworkError(f"NEIS HTTP 요청 실패 (상태 {exc.code}).") from None
        except (URLError, TimeoutError, OSError):
            raise NEISNetworkError("NEIS 서버에 연결할 수 없습니다.") from None
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise NEISResponseError("NEIS가 유효하지 않은 JSON을 반환했습니다.") from None
        if not isinstance(payload, dict):
            raise NEISResponseError("NEIS 응답 형식이 올바르지 않습니다.")

        def check_result(result: Any) -> bool:
            if not isinstance(result, dict) or not isinstance(result.get("CODE"), str):
                raise NEISResponseError("NEIS 결과 코드가 없습니다.")
            code = result["CODE"]
            if code == "INFO-200":
                return False
            if code != "INFO-000":
                raise NEISAPIError("NEIS가 요청을 거부했습니다.")
            return True

        if "RESULT" in payload:
            if not check_result(payload["RESULT"]):
                return [], 0
            raise NEISResponseError("NEIS 데이터가 없습니다.")
        blocks = payload.get(endpoint)
        if not isinstance(blocks, list):
            raise NEISResponseError("NEIS 응답 형식이 올바르지 않습니다.")
        head = next((b["head"] for b in blocks if isinstance(b, dict) and "head" in b), None)
        if not isinstance(head, list):
            raise NEISResponseError("NEIS 응답 헤더가 없습니다.")
        result = next((h["RESULT"] for h in head if isinstance(h, dict) and "RESULT" in h), None)
        if not check_result(result):
            return [], 0
        count = next((h["list_total_count"] for h in head if isinstance(h, dict) and "list_total_count" in h), None)
        rows = next((b["row"] for b in blocks if isinstance(b, dict) and "row" in b), None)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0 or not isinstance(rows, list):
            raise NEISResponseError("NEIS 응답의 건수 또는 데이터가 올바르지 않습니다.")
        if any(not isinstance(row, dict) for row in rows):
            raise NEISResponseError("NEIS 데이터 형식이 올바르지 않습니다.")
        return rows, count

    def _all_rows(self, endpoint: str, params: dict[str, str]) -> list[dict]:
        result: list[dict] = []
        page = 1
        total = None
        while True:
            rows, count = self._request(endpoint, {**params, "pIndex": str(page), "pSize": "1000"})
            if total is not None and count != total:
                raise NEISResponseError("NEIS 조회 도중 전체 건수가 변경되었습니다.")
            total = count
            result.extend(rows)
            if len(result) == count:
                return result
            if not rows or len(result) > count:
                raise NEISResponseError("NEIS가 전체 결과를 반환하지 않았습니다.")
            page += 1

    def search_schools(self, name: str, *, office_code: str | None = None) -> list[School]:
        """Return candidates; never infer identity from the name alone."""
        name = name.strip()
        if not name:
            raise ValueError("학교명을 입력해 주세요.")
        params = {"SCHUL_NM": name}
        if office_code:
            params["ATPT_OFCDC_SC_CODE"] = office_code
        result = []
        for row in self._all_rows("schoolInfo", params):
            office = row.get("ATPT_OFCDC_SC_CODE")
            code = row.get("SD_SCHUL_CODE")
            if (not isinstance(office, str) or not re.fullmatch(r"[A-Z][0-9]{2}", office)
                    or not isinstance(code, str) or not re.fullmatch(r"[0-9]{7}", code)
                    or not isinstance(row.get("SCHUL_NM"), str) or not row["SCHUL_NM"].strip()):
                raise NEISResponseError("NEIS 학교 정보가 올바르지 않습니다.")
            result.append(School(row["ATPT_OFCDC_SC_CODE"], row["SD_SCHUL_CODE"], row["SCHUL_NM"], row.get("SCHUL_KND_SC_NM"), row.get("ORG_RDNMA")))
        return result

    def get_meals(self, school: School, start: date, end: date) -> list[Meal]:
        """Return meals for the inclusive date range. Menu retains allergy markers."""
        if not school.office_code or not school.school_code:
            raise ValueError("NEIS 교육청 코드와 학교 코드가 필요합니다.")
        if end < start:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        rows = self._all_rows("mealServiceDietInfo", {
            "ATPT_OFCDC_SC_CODE": school.office_code,
            "SD_SCHUL_CODE": school.school_code,
            "MLSV_FROM_YMD": start.strftime("%Y%m%d"),
            "MLSV_TO_YMD": end.strftime("%Y%m%d"),
        })
        result = []
        for row in rows:
            try:
                meal_date = date.fromisoformat(row["MLSV_YMD"]).isoformat()
                menu = row["DDISH_NM"]
                if not isinstance(menu, str):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise NEISResponseError("NEIS 급식 데이터가 올바르지 않습니다.") from None
            result.append(Meal(meal_date, row.get("MMEAL_SC_NM") or "", menu, row.get("CAL_INFO"), row.get("ORPLC_INFO")))
        return result
