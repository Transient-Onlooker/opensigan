import json
import time

from workers import Response, WorkerEntrypoint

attempted = False


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global attempted
        started = time.perf_counter()
        try:
            if attempted:
                raise RuntimeError("single attempt already used")
            attempted = True
            from pycomcigan import get_school_code

            count = len(get_school_code("서울"))
            result = {"success": True, "count": count, "error_type": None}
        except Exception as exc:
            result = {"success": False, "count": None, "error_type": type(exc).__name__}
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return Response(json.dumps(result), headers={"content-type": "application/json"})
