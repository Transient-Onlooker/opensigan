import os
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.app import Handler
from backend.cache import Cache
from backend.neis import Meal, School


ROOT = Path(__file__).resolve().parents[2]

NODE_TEST = r"""
const assert = require('node:assert/strict');

(async () => {
  globalThis.location = { hostname: 'localhost' };
  const { createServer } = await import('vite');
  const vite = await createServer({
    configFile: false,
    root: process.cwd(),
    envDir: process.env.TEST_TEMP_DIR,
    cacheDir: process.env.TEST_TEMP_DIR,
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    const api = await vite.ssrLoadModule('/src/api.ts');
    assert.deepEqual(await api.searchSchools('서울 학교'), {
      schools: [{ id: '2:서울 학교', name: '서울 학교', region: '서울' }], stale: false,
    });
    assert.deepEqual(await api.searchNeisSchools('서울 학교'), {
      schools: [{ id: 'B10:1234567', name: '서울 학교', region: '고등학교', address: '서울' }], stale: false,
    });
    assert.deepEqual(await api.getTimetable('2:서울 학교', '2026-11-09'), {
      schoolId: '2:서울 학교', weekStart: '2026-11-09', records: [],
      sourceUpdatedAt: null, fetchedAt: '2026-11-10T00:00:00Z', stale: false, cacheStatus: 'miss',
    });
    assert.deepEqual(await api.getMeals('B10:1234567', '2026-11-09', '2026-11-15'), {
      meals: [{ date: '2026-11-10', type: '중식', dishes: ['밥(1)', '국(2)'] }], stale: false,
    });
    await assert.rejects(api.getMeals('invalid', '2026-11-09', '2026-11-15'), /400/);
    await assert.rejects(api.searchSchools('failure'), /503/);
  } finally {
    await vite.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


class FrontendHttpTests(unittest.TestCase):
    def test_frontend_client_against_local_backend(self):
        def schools(query):
            if query == "failure":
                raise RuntimeError("fixture failure")
            return [{"id": "2:서울 학교", "name": query, "region": "서울"}]

        timetable = {"schoolId": "2:서울 학교", "weekStart": "2026-11-09", "records": [],
                     "sourceUpdatedAt": None, "fetchedAt": "2026-11-10T00:00:00Z", "stale": False}
        temp_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Temp" if os.name == "nt" else None
        with tempfile.TemporaryDirectory(prefix="opensigan-http-", dir=temp_root) as temp_dir, \
                patch("backend.app.cache", Cache()), \
                patch("backend.app.search_schools", side_effect=schools) as search, \
                patch("backend.app.validate_timetable_week") as validate, \
                patch("backend.app.fetch_timetable", return_value=timetable) as fetch_timetable, \
                patch("backend.app.NEISClient.from_environment") as neis, \
                patch.dict(os.environ, {"NEIS_API_KEY": "fixture-key"}):
            neis.return_value.search_schools.return_value = [School("B10", "1234567", "서울 학교", "고등학교", "서울")]
            neis.return_value.get_meals.return_value = [Meal("2026-11-10", "중식", "밥(1)<br/>국(2)")]
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = {key: value for key, value in os.environ.items() if not key.startswith("VITE_")}
                env.update(VITE_API_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                           TEST_TEMP_DIR=temp_dir, TEMP=temp_dir, TMP=temp_dir)
                result = subprocess.run(["node", "-e", NODE_TEST], cwd=ROOT / "frontend", env=env,
                                        capture_output=True, text=True, encoding="utf-8", timeout=45)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([call.args[0] for call in search.call_args_list], ["서울 학교", "failure"])
                neis.return_value.search_schools.assert_called_once_with("서울 학교")
                validate.assert_called_once_with("2026-11-09")
                fetch_timetable.assert_called_once_with("2:서울 학교", "2026-11-09")
                meal_args = neis.return_value.get_meals.call_args.args
                self.assertEqual((meal_args[0].office_code, meal_args[0].school_code), ("B10", "1234567"))
                self.assertEqual(tuple(map(str, meal_args[1:])), ("2026-11-09", "2026-11-15"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
