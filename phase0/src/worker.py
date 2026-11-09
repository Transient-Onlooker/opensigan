import json
import time

from workers import Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        started = time.perf_counter()
        try:
            from pycomcigan import TimeTable, get_school_code
        except Exception as exc:
            result = {"import_ok": False, "error_type": type(exc).__name__}
        else:
            result = {
                "import_ok": True,
                "TimeTable_callable": callable(TimeTable),
                "get_school_code_callable": callable(get_school_code),
            }
        result["import_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return Response(json.dumps(result), headers={"content-type": "application/json"})
