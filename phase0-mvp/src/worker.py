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
            from pycomcigan import get_school_code

            count = len(get_school_code("서울"))
            result = {"success": True, "count": count, "error_type": None}
        except Exception as exc:
            result = {"success": False, "count": None, "error_type": type(exc).__name__}
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return Response(json.dumps(result), headers={"content-type": "application/json"})
