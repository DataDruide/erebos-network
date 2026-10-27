#!/usr/bin/env python3
"""Erebos Service CLI — eigene Hidden Services verwalten."""
import argparse
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


def _load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {}


def _save_registry(data: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, indent=2))


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_create(args) -> int:
    registry = _load_registry()
    if args.name in registry:
        print(f"FEHLER: Service '{args.name}' existiert schon")
        return 1

    pages = Path(args.pages).resolve()
    if not pages.exists():
        print(f"FEHLER: Pages-Verzeichnis '{pages}' existiert nicht")
        return 1

    key_file = SERVICES_DIR / f"{args.name}.pem"
    log_file = LOGS_DIR / f"{args.name}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-u",
        str(Path(__file__).parent / "create_hidden_service.py"),
        "--name", args.name,
        "--port", str(args.port),
        "--pages", str(pages),
        "--key-file", str(key_file),
        "--bind-host", "0.0.0.0",
        "--log-level", args.log_level,
    ]

    print(f"[*] Starte Service '{args.name}' auf Port {args.port}...")
    print(f"[*] Pages: {pages}")
    print(f"[*] Log: {log_file}")

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
            print(f"FEHLER: Service gecrasht. Log:")
            print(log_file.read_text()[-2000:])
            return 1

    if not address:
        print(f"WARNUNG: Adresse nicht gefunden. Log:")
        print(log_file.read_text()[-1000:])

    registry[args.name] = {
        "pid": proc.pid,
        "port": args.port,
        "pages": str(pages),
        "address": address or "(unbekannt)",
        "key_file": str(key_file),
        "log_file": str(log_file),
        "created_at": time.time(),
    }
    _save_registry(registry)

    print()
    print(f"OK: Service '{args.name}' läuft")
    print(f"    PID:     {proc.pid}")
    print(f"    Port:    {args.port}")
    print(f"    Adresse: {address}")
    print()
    print(f"Im Browser (mit SOCKS5-Proxy 127.0.0.1:4448):")
    print(f"    http://{address}/")
    return 0


def cmd_list(args) -> int:
    registry = _load_registry()
    if not registry:
        print("Keine Services registriert.")
        return 0

    print(f"{'NAME':<20} {'PORT':<6} {'STATUS':<10} {'ADRESSE':<60}")
    print("-" * 100)
    for name, info in registry.items():
        status = "läuft" if _is_running(info["pid"]) else "gestoppt"
        print(f"{name:<20} {info['port']:<6} {status:<10} {info['address']:<60}")
    return 0


def cmd_stop(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1

    info = registry[args.name]
    pid = info["pid"]
    if not _is_running(pid):
        print(f"Service '{args.name}' läuft nicht (PID {pid})")
        return 0

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        print(f"OK: Service '{args.name}' gestoppt (PID {pid})")
    except Exception as e:
        print(f"FEHLER: {e}")
        return 1
    return 0


def cmd_delete(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1

    info = registry[args.name]
    pid = info["pid"]
    if _is_running(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            pass

    key_file = Path(info.get("key_file", ""))
    if key_file.exists() and args.delete_key:
        key_file.unlink()
        print(f"OK: Key gelöscht: {key_file}")

    del registry[args.name]
    _save_registry(registry)
    print(f"OK: Service '{args.name}' gelöscht")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Erebos Service CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Neuen Service erstellen")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--port", type=int, required=True)
    p_create.add_argument("--pages", required=True, help="Verzeichnis mit HTML-Dateien")
    p_create.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="Services auflisten")
    p_list.set_defaults(func=cmd_list)

    p_stop = sub.add_parser("stop", help="Service stoppen")
    p_stop.add_argument("--name", required=True)
    p_stop.set_defaults(func=cmd_stop)

    p_delete = sub.add_parser("delete", help="Service löschen")
    p_delete.add_argument("--name", required=True)
    p_delete.add_argument("--delete-key", action="store_true", help="Auch den Ed25519-Key löschen")
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
