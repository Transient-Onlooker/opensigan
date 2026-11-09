import json
import time

from workers import Response, WorkerEntrypoint

attempted = False


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global attempted
        started = time.perf_counter()
        try:
            if request.url.endswith("/import-check"):
                from Cryptodome.Cipher import AES
                from pycomcigan import get_school_code

                key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
                plain = bytes.fromhex("00112233445566778899aabbccddeeff")
                assert AES.new(key, AES.MODE_ECB).encrypt(plain).hex() == "69c4e0d86a7b0430d8cdb78070b4c55a"
                return Response(json.dumps({"import_ok": callable(get_school_code), "aes_ok": True}),
                                headers={"content-type": "application/json"})
            if attempted:
                raise RuntimeError("single attempt already used")
            attempted = True
            if request.url.endswith("/timetable"):
                from pycomcigan import TimeTable

                school_name = await request.text()
                table = TimeTable(school_name, week_num=0)
                count = 0
                changed = 0
                for classes in table.timetable:
                    for days in classes:
                        for lessons in days[1:6]:
                            for lesson in lessons:
                                if not isinstance(lesson.replaced, bool):
                                    raise TypeError("invalid change flag")
                                if not isinstance(lesson.subject, str) or not isinstance(lesson.teacher, str):
                                    raise TypeError("invalid lesson")
                                if lesson.subject or lesson.teacher or lesson.replaced:
                                    count += 1
                                    changed += int(lesson.replaced)
                result = {"success": True, "count": count, "changed_count": changed,
                          "change_flag_present": count > 0, "error_type": None}
                result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                return Response(json.dumps(result), headers={"content-type": "application/json"})
            from pycomcigan import get_school_code

            count = len(get_school_code("서울"))
            result = {"success": True, "count": count, "error_type": None}
        except Exception as exc:
            result = {"success": False, "count": None, "changed_count": None,
                      "change_flag_present": None, "error_type": type(exc).__name__}
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return Response(json.dumps(result), headers={"content-type": "application/json"})
