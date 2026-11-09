import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

root = Path(__file__).resolve().parent
runtime = root / ".runtime"
runtime.mkdir(exist_ok=True)
for name in ("cache", "tmp", "config", "npm"):
    (runtime / name).mkdir(exist_ok=True)
env = os.environ.copy()
env["PATH"] = str(root / ".venv" / "Scripts") + os.pathsep + env["PATH"]
env.update({"PYTHONUTF8": "1", "WRANGLER_SEND_METRICS": "false",
            "UV_CACHE_DIR": str(runtime / "cache"), "XDG_CACHE_HOME": str(runtime / "cache"),
            "XDG_CONFIG_HOME": str(runtime / "config"), "npm_config_cache": str(runtime / "npm"),
            "TEMP": str(runtime / "tmp"), "TMP": str(runtime / "tmp")})
ready = threading.Event()
events = []
output = []
server = None
collector = None
result = None


def collect(pipe):
    for line in iter(pipe.readline, ""):
        output.append(line)
        lowered = line.lower()
        for phrase in ("failed to download", "failed to fetch", "failed to install", "failed to build",
                       "no solution found", "invalid peer certificate", "access is denied", "os error 5",
                       "error running command", "no matching distribution", "not supported",
                       "could not find", "failed to create", "no-build", "not found"):
            if phrase in lowered:
                events.append("diagnostic:" + phrase)
        if "ready on" in lowered:
            events.append("server_ready")
            ready.set()
        if "error" in lowered or "exception" in lowered:
            events.append("server_error_output")
            for word in ("uv", "version", "pylock", "git", "wheel", "permission", "timeout",
                         "network", "certificate", "wrangler", "python", "dependency", "package"):
                if word in lowered:
                    events.append("error_context:" + word)


try:
    server = subprocess.Popen([str(root / ".venv" / "Scripts" / "pywrangler.exe"), "dev", "--local",
                               "--ip", "127.0.0.1", "--port", "18787"], cwd=root, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace")
    collector = threading.Thread(target=collect, args=(server.stdout,), daemon=True)
    collector.start()
    deadline = time.monotonic() + 60
    while not ready.is_set() and server.poll() is None and time.monotonic() < deadline:
        ready.wait(0.1)
    if not ready.is_set():
        events.append("server_exited" if server.poll() is not None else "startup_timeout")
    else:
        started = time.monotonic()
        watchdog = threading.Timer(45, lambda: subprocess.run(
            ["taskkill", "/PID", str(server.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10))
        watchdog.start()
        try:
            path = "/import-check" if "--import-only" in sys.argv else "/"
            with urllib.request.urlopen("http://127.0.0.1:18787" + path, timeout=45) as response:
                payload = json.load(response)
            if path == "/import-check":
                result = {"success": payload.get("import_ok") is True and payload.get("aes_ok") is True,
                          "import_ok": payload.get("import_ok"), "aes_ok": payload.get("aes_ok")}
            else:
                result = {key: payload[key] for key in ("success", "count", "elapsed_ms", "error_type")}
        except Exception as exc:
            result = {"success": False, "count": None,
                      "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                      "error_type": type(exc).__name__}
        finally:
            watchdog.cancel()
        if not result["success"]:
            events.append("request_error:" + str(result["error_type"]))
except Exception as exc:
    events.append("runner_error:" + type(exc).__name__)
finally:
    if server is not None and server.poll() is None:
        subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    if collector is not None:
        collector.join(timeout=10)
    (root / "run.log").write_text("".join(output), encoding="utf-8")
    report = {"events": events, "server_exit_code": server.poll() if server else None, "response": result}
    (root / "run-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if not result or not result["success"]:
    sys.exit(1)
