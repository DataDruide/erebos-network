"""Service-Manager: startet/stoppt/löscht Hidden Services.

Nutzt dieselbe Registry wie scripts/erebos_service.py
(~/.erebos/services/registry.json).
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SERVICES_DIR = Path.home() / ".erebos" / "services"
LOGS_DIR = SERVICES_DIR / "logs"
REGISTRY = SERVICES_DIR / "registry.json"


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {}


def save_registry(data: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, indent=2))


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def list_services() -> list[dict]:
    """Gibt alle Services als Liste zurück (mit Status)."""
    registry = load_registry()
    result = []
    for name, info in registry.items():
        result.append({
            "name": name,
            "port": info["port"],
            "address": info["address"],
            "pages": info["pages"],
            "status": "läuft" if is_running(info["pid"]) else "gestoppt",
            "pid": info["pid"],
        })
    return result


def create_service(name: str, port: int, pages: str) -> dict:
    """Startet einen neuen Service. Gibt {'ok': bool, 'message': str, 'address': str} zurück."""
    registry = load_registry()
    if name in registry:
        return {"ok": False, "message": f"Service '{name}' existiert schon"}

    pages_path = Path(pages).resolve()
    if not pages_path.exists():
        return {"ok": False, "message": f"Verzeichnis '{pages}' existiert nicht"}

    key_file = SERVICES_DIR / f"{name}.pem"
    log_file = LOGS_DIR / f"{name}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-u",
        str(Path(__file__).parent.parent.parent / "scripts" / "create_hidden_service.py"),
        "--name", name,
        "--port", str(port),
        "--pages", str(pages_path),
        "--key-file", str(key_file),
        "--bind-host", "0.0.0.0",
        "--log-level", "INFO",
    ]

    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    address = None
    for _ in range(20):
        time.sleep(0.5)
        if log_file.exists():
            content = log_file.read_text()
            for line in content.splitlines():
                if "Hidden Service läuft:" in line:
                    address = line.split("Hidden Service läuft:")[-1].strip()
                    break
        if address:
            break
        if proc.poll() is not None:
            return {"ok": False, "message": f"Service gecrasht. Log: {log_file}"}

    registry[name] = {
        "pid": proc.pid,
        "port": port,
        "pages": str(pages_path),
        "address": address or "(unbekannt)",
        "key_file": str(key_file),
        "log_file": str(log_file),
        "created_at": time.time(),
    }
    save_registry(registry)

    return {"ok": True, "message": "Service läuft", "address": address}


def stop_service(name: str) -> dict:
    registry = load_registry()
    if name not in registry:
        return {"ok": False, "message": f"Service '{name}' nicht gefunden"}

    info = registry[name]
    pid = info["pid"]
    if not is_running(pid):
        return {"ok": True, "message": "Service läuft nicht"}

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return {"ok": True, "message": f"Service '{name}' gestoppt"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def delete_service(name: str, delete_key: bool = False) -> dict:
    registry = load_registry()
    if name not in registry:
        return {"ok": False, "message": f"Service '{name}' nicht gefunden"}

    info = registry[name]
    pid = info["pid"]
    if is_running(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            pass

    key_file = Path(info.get("key_file", ""))
    if key_file.exists() and delete_key:
        key_file.unlink()

    del registry[name]
    save_registry(registry)
    return {"ok": True, "message": f"Service '{name}' gelöscht"}

def get_pages_dir(name: str):
    """Gibt das pages/-Verzeichnis eines Services zurück (oder None)."""
    registry = load_registry()
    if name not in registry:
        return None
    return Path(registry[name]["pages"])


def list_files(name: str) -> list[str]:
    """Listet alle Dateien im pages/-Verzeichnis eines Services."""
    pages_dir = get_pages_dir(name)
    if pages_dir is None or not pages_dir.exists():
        return []
    return sorted([f.name for f in pages_dir.iterdir() if f.is_file()])


def upload_file(name: str, filename: str, content: bytes) -> dict:
    """Speichert eine Datei im pages/-Verzeichnis des Services."""
    registry = load_registry()
    if name not in registry:
        return {"ok": False, "message": f"Service '{name}' nicht gefunden"}

    pages_dir = Path(registry[name]["pages"])
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Path-Traversal verhindern
    safe_name = Path(filename).name
    if not safe_name or safe_name.startswith("."):
        return {"ok": False, "message": "Ungültiger Dateiname"}

    # Endung prüfen
    allowed = {".html", ".htm", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".txt"}
    if Path(safe_name).suffix.lower() not in allowed:
        return {"ok": False, "message": f"Dateityp nicht erlaubt: {safe_name}"}

    target = pages_dir / safe_name
    target.write_bytes(content)
    return {"ok": True, "message": f"Datei '{safe_name}' hochgeladen", "path": str(target)}



def start_service(name: str) -> dict:
    """Startet einen Service aus der Registry."""
    registry = load_registry()
    if name not in registry:
        return {"ok": False, "message": f"Service '{name}' nicht gefunden"}
    info = registry[name]
    if is_running(info["pid"]):
        return {"ok": True, "message": f"Service '{name}' läuft bereits"}
    # Service neu starten (create_hidden_service.py)
    script = Path(__file__).parent.parent.parent / "scripts" / "create_hidden_service.py"
    log_file = LOGS_DIR / f"{name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-u", str(script),
        "--name", name,
        "--port", str(info["port"]),
        "--pages", str(info["pages"]),
        "--key-file", str(info.get("key_file", "")),
        "--bind-host", "0.0.0.0",
        "--log-level", info.get("log_level", "INFO"),
    ]
    log_handle = open(log_file, "a")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, start_new_session=True)
    time.sleep(2)
    if is_running(proc.pid):
        info["pid"] = proc.pid
        save_registry(registry)
        return {"ok": True, "message": f"Service '{name}' gestartet (PID {proc.pid})"}
    return {"ok": False, "message": f"Service '{name}' konnte nicht gestartet werden"}


def restart_service(name: str) -> dict:
    """Stoppt und startet einen Service neu."""
    stop_result = stop_service(name)
    time.sleep(1)
    return start_service(name)


def get_logs(name: str, lines: int = 50) -> list[str]:
    """Gibt die letzten N Zeilen des Service-Logs zurück."""
    log_file = LOGS_DIR / f"{name}.log"
    if not log_file.exists():
        return [f"Log-Datei '{log_file}' existiert nicht"]
    try:
        with open(log_file) as f:
            all_lines = f.readlines()
        return [line.rstrip() for line in all_lines[-lines:]]
    except Exception as e:
        return [f"Fehler: {e}"]


def get_health(name: str) -> dict:
    """Prüft die Erreichbarkeit eines Service."""
    registry = load_registry()
    if name not in registry:
        return {"ok": False, "message": f"Service '{name}' nicht gefunden"}
    info = registry[name]
    port = info["port"]
    import urllib.request
    try:
        url = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return {"ok": True, "status": resp.status, "port": port}
    except urllib.error.HTTPError as e:
        return {"ok": True, "status": e.code, "port": port}
    except Exception as e:
        return {"ok": False, "message": str(e), "port": port}
