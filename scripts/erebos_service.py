#!/usr/bin/env python3
"""Erebos Service CLI — eigene Hidden Services verwalten.

Native Welt: startet Hidden-Service-Prozesse direkt auf dem Host
(sys.executable), nicht in Docker. Fuer den Docker-Stack siehe
docker-compose.yml.

Kommandos:
  create   Neuen Service anlegen und starten
  list     Registrierte Services auflisten
  start    Registrierten Service (wieder) starten
  stop     Laufenden Service stoppen
  delete   Service aus der Registry entfernen (optional Key loeschen)
  status   Detaillierter Status (PID, Log, Descriptor, SOCKS5-Test)
  test     SOCKS5-Test gegen die Service-Adresse (Exit 0/1)
  logs     Log des Service verfolgen (tail -f)
"""
import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

SERVICES_DIR = Path.home() / ".erebos" / "services"
LOGS_DIR = SERVICES_DIR / "logs"
REGISTRY = SERVICES_DIR / "registry.json"

# Defaults fuer die native Welt (127.0.0.1). Fuer Docker/andere Setups
# koennen sie per CLI ueberschrieben werden.
DEFAULTS = {
    "rendezvous_host": "127.0.0.1",
    "rendezvous_port": 9999,
    "bind_host": "0.0.0.0",
    "dht_peers": "127.0.0.1:9999,127.0.0.1:9998,127.0.0.1:9997",
    "intro_points": "peer1:127.0.0.1:9999,peer2:127.0.0.1:9998,peer3:127.0.0.1:9997",
    "log_level": "INFO",
}

PROXY = ("127.0.0.1", 4448)


def _python_exe() -> str:
    """Bevorzugt .venv/bin/python im Repo-Root, sonst sys.executable."""
    repo_root = Path(__file__).resolve().parent.parent
    venv_py = repo_root / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _subprocess_env() -> dict:
    """Environment fuer create_hidden_service.py: PYTHONPATH=src ergaenzen."""
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    src = str(repo_root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


# --- Registry-Helfer -------------------------------------------------------

def _load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text())
        except json.JSONDecodeError:
            return {}
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


# --- Service-Start-Helfer --------------------------------------------------

def _build_create_cmd(name: str, port: int, pages: Path, key_file: Path,
                      opts: dict) -> list:
    return [
        _python_exe(), "-u",
        str(Path(__file__).parent / "create_hidden_service.py"),
        "--name", name,
        "--port", str(port),
        "--pages", str(pages),
        "--key-file", str(key_file),
        "--bind-host", opts["bind_host"],
        "--log-level", opts["log_level"],
        "--rendezvous-host", opts["rendezvous_host"],
        "--rendezvous-port", str(opts["rendezvous_port"]),
        "--dht-peers", opts["dht_peers"],
        "--intro-points", opts["intro_points"],
    ]


def _wait_for_address(log_file: Path, proc: subprocess.Popen,
                      timeout: float = 15.0) -> str | None:
    """Wartet auf 'Hidden Service läuft: <addr>' im Log. None bei Timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        if log_file.exists():
            try:
                content = log_file.read_text(errors="replace")
            except OSError:
                content = ""
            for line in content.splitlines():
                if "Hidden Service läuft:" in line:
                    return line.split("Hidden Service läuft:")[-1].strip()
        if proc.poll() is not None:
            return None
    return None


# --- SOCKS5-Test-Helfer ----------------------------------------------------

def _socks5_get(address: str, port: int = 80, timeout: float = 15.0):
    """Fuehrt einen SOCKS5-CONNECT + HTTP-GET gegen <address>:<port> aus.

    Rueckgabe: (ok: bool, detail: str)
    """
    host = address.strip()
    if host.endswith(".erebos"):
        target_host = host
    else:
        target_host = host

    try:
        s = socket.create_connection(PROXY, timeout=timeout)
    except OSError as e:
        return False, f"Proxy nicht erreichbar ({PROXY[0]}:{PROXY[1]}): {e}"

    try:
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")
        hs = s.recv(2)
        if hs != b"\x05\x00":
            return False, f"SOCKS5-Handshake fehlgeschlagen: {hs.hex()}"

        hb = target_host.encode()
        req = b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack("!H", port)
        s.sendall(req)
        reply = s.recv(10)
        if len(reply) < 2:
            return False, f"SOCKS5-Reply zu kurz: {reply.hex()}"
        if reply[1] != 0:
            return False, f"SOCKS5-REP=0x{reply[1]:02x}"

        s.sendall(b"GET / HTTP/1.1\r\nHost: " + hb + b"\r\nConnection: close\r\n\r\n")
        data = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass

        if not data:
            return False, "SOCKS5-REP=SUCCESS, aber keine HTTP-Antwort"
        status = data.split(b"\r\n", 1)[0].decode("utf-8", "replace")
        return True, status
    except Exception as e:
        return False, f"Fehler: {e}"
    finally:
        try:
            s.close()
        except Exception:
            pass


# --- Kommandos -------------------------------------------------------------

def cmd_create(args) -> int:
    registry = _load_registry()
    if args.name in registry:
        print(f"FEHLER: Service '{args.name}' existiert schon "
              f"(nutze 'start --name {args.name}' oder 'delete')")
        return 1

    pages = Path(args.pages).resolve()
    if not pages.exists():
        print(f"FEHLER: Pages-Verzeichnis '{pages}' existiert nicht")
        return 1

    key_file = SERVICES_DIR / f"{args.name}.pem"
    log_file = LOGS_DIR / f"{args.name}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    opts = {
        "rendezvous_host": args.rendezvous_host,
        "rendezvous_port": args.rendezvous_port,
        "bind_host": args.bind_host,
        "dht_peers": args.dht_peers,
        "intro_points": args.intro_points,
        "log_level": args.log_level,
    }
    cmd = _build_create_cmd(args.name, args.port, pages, key_file, opts)

    print(f"[*] Starte Service '{args.name}' auf Port {args.port}...")
    print(f"[*] Pages: {pages}")
    print(f"[*] Log:   {log_file}")

    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_subprocess_env(),
        )

    address = _wait_for_address(log_file, proc)
    if not address:
        print(f"FEHLER: Adresse nicht gefunden oder Service gecrasht. Log:")
        try:
            print(log_file.read_text(errors="replace")[-2000:])
        except OSError:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        return 1

    registry[args.name] = {
        "pid": proc.pid,
        "port": args.port,
        "pages": str(pages),
        "address": address,
        "key_file": str(key_file),
        "log_file": str(log_file),
        "created_at": time.time(),
        **opts,
    }
    _save_registry(registry)

    print()
    print(f"OK: Service '{args.name}' laeuft")
    print(f"    PID:     {proc.pid}")
    print(f"    Port:    {args.port}")
    print(f"    Adresse: {address}")
    print()
    print(f"Im Browser (SOCKS5-Proxy {PROXY[0]}:{PROXY[1]}):")
    print(f"    http://{address}/")
    print()
    print("Key sichern (Identitaet = Adresse):")
    print(f"    {key_file}")
    return 0


def cmd_list(args) -> int:
    registry = _load_registry()
    if not registry:
        print("Keine Services registriert.")
        return 0

    print(f"{'NAME':<20} {'PORT':<6} {'STATUS':<10} {'ADRESSE':<60}")
    print("-" * 100)
    for name, info in registry.items():
        status = "läuft" if _is_running(info.get("pid", -1)) else "gestoppt"
        addr = info.get("address", "(unbekannt)")
        print(f"{name:<20} {info.get('port', '-'):<6} {status:<10} {addr:<60}")
    return 0


def cmd_start(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden "
              f"(nutze 'create' zum Anlegen)")
        return 1
    info = registry[args.name]
    pid = info.get("pid", -1)
    if _is_running(pid):
        print(f"Service '{args.name}' laeuft bereits (PID {pid})")
        return 0

    key_file = Path(info["key_file"])
    log_file = Path(info["log_file"])
    pages = Path(info["pages"])
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not pages.exists():
        print(f"FEHLER: Pages-Verzeichnis '{pages}' fehlt")
        return 1

    opts = {
        "rendezvous_host": info.get("rendezvous_host", DEFAULTS["rendezvous_host"]),
        "rendezvous_port": info.get("rendezvous_port", DEFAULTS["rendezvous_port"]),
        "bind_host": info.get("bind_host", DEFAULTS["bind_host"]),
        "dht_peers": info.get("dht_peers", DEFAULTS["dht_peers"]),
        "intro_points": info.get("intro_points", DEFAULTS["intro_points"]),
        "log_level": info.get("log_level", DEFAULTS["log_level"]),
    }
    cmd = _build_create_cmd(args.name, info["port"], pages, key_file, opts)

    print(f"[*] Starte Service '{args.name}' (Port {info['port']})...")
    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_subprocess_env(),
        )

    address = _wait_for_address(log_file, proc)
    if not address:
        print(f"FEHLER: Adresse nicht gefunden oder Service gecrasht. Log:")
        try:
            print(log_file.read_text(errors="replace")[-2000:])
        except OSError:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        return 1

    info["pid"] = proc.pid
    info["address"] = address
    registry[args.name] = info
    _save_registry(registry)

    print(f"OK: Service '{args.name}' laeuft wieder")
    print(f"    PID:     {proc.pid}")
    print(f"    Adresse: {address} (stabil, da Key unveraendert)")
    return 0


def cmd_stop(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1
    info = registry[args.name]
    pid = info.get("pid", -1)
    if not _is_running(pid):
        print(f"Service '{args.name}' laeuft nicht (PID {pid})")
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
    pid = info.get("pid", -1)
    if _is_running(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            pass
    key_file = Path(info.get("key_file", ""))
    if args.delete_key and key_file.exists():
        key_file.unlink()
        print(f"OK: Key geloescht: {key_file}")
        print("     ACHTUNG: Die .erebos-Adresse ist damit dauerhaft weg.")
    del registry[args.name]
    _save_registry(registry)
    print(f"OK: Service '{args.name}' aus Registry entfernt")
    return 0


def cmd_status(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1
    info = registry[args.name]
    pid = info.get("pid", -1)
    running = _is_running(pid)
    addr = info.get("address", "(unbekannt)")
    log_file = Path(info.get("log_file", ""))

    print(f"Service:  {args.name}")
    print(f"PID:      {pid} ({'laeuft' if running else 'gestoppt'})")
    print(f"Port:     {info.get('port', '-')}")
    print(f"Pages:    {info.get('pages', '-')}")
    print(f"Key:      {info.get('key_file', '-')}")
    print(f"Adresse:  {addr}")
    print(f"Log:      {log_file}")

    # Log-Tail
    if log_file.exists():
        try:
            tail = log_file.read_text(errors="replace").splitlines()[-5:]
        except OSError:
            tail = []
        if tail:
            print()
            print("Letzte Log-Zeilen:")
            for line in tail:
                print(f"  {line}")

        try:
            content = log_file.read_text(errors="replace")
        except OSError:
            content = ""
        descriptor_ok = "Descriptor veröffentlicht in DHT" in content
        rendezvous_ok = "Rendezvous-Paar vollständig!" in content
        print()
        print(f"Descriptor publiziert:     {'ja' if descriptor_ok else 'nein/unbekannt'}")
        print(f"Rendezvous vollstaendig:   {'ja' if rendezvous_ok else 'nein/unbekannt'}")

    if not running:
        print()
        print("Hinweis: Service laeuft nicht. 'start' zum Wieder-Starten.")
        return 1

    # SOCKS5-Test nur, wenn Adresse bekannt
    if addr and addr != "(unbekannt)":
        ok, detail = _socks5_get(addr)
        print()
        if ok:
            print(f"Erreichbarkeit: OK ({detail})")
            return 0
        print(f"Erreichbarkeit: NICHT ERREICHBAR ({detail})")
        return 1
    return 0


def cmd_test(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1
    info = registry[args.name]
    addr = info.get("address", "")
    if not addr:
        print(f"FEHLER: Keine Adresse fuer '{args.name}' in Registry")
        return 1
    ok, detail = _socks5_get(addr)
    print(f"Test gegen {addr}:")
    print(f"  {'OK' if ok else 'FEHLER'}: {detail}")
    return 0 if ok else 1


def cmd_logs(args) -> int:
    registry = _load_registry()
    if args.name not in registry:
        print(f"FEHLER: Service '{args.name}' nicht gefunden")
        return 1
    log_file = Path(registry[args.name]["log_file"])
    if not log_file.exists():
        print(f"FEHLER: Log-Datei fehlt: {log_file}")
        return 1
    try:
        subprocess.run(["tail", "-n", str(args.lines), "-f", str(log_file)])
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Erebos Service CLI (native Welt)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Neuen Service anlegen und starten")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--port", type=int, required=True)
    p_create.add_argument("--pages", required=True, help="Verzeichnis mit HTML-Dateien")
    p_create.add_argument("--rendezvous-host", default=DEFAULTS["rendezvous_host"])
    p_create.add_argument("--rendezvous-port", type=int, default=DEFAULTS["rendezvous_port"])
    p_create.add_argument("--bind-host", default=DEFAULTS["bind_host"])
    p_create.add_argument("--dht-peers", default=DEFAULTS["dht_peers"])
    p_create.add_argument("--intro-points", default=DEFAULTS["intro_points"])
    p_create.add_argument("--log-level", default=DEFAULTS["log_level"],
                          choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="Services auflisten")
    p_list.set_defaults(func=cmd_list)

    p_start = sub.add_parser("start", help="Registrierten Service starten")
    p_start.add_argument("--name", required=True)
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="Service stoppen")
    p_stop.add_argument("--name", required=True)
    p_stop.set_defaults(func=cmd_stop)

    p_delete = sub.add_parser("delete", help="Service entfernen")
    p_delete.add_argument("--name", required=True)
    p_delete.add_argument("--delete-key", action="store_true",
                          help="Auch den Ed25519-Key loeschen (Adresse wird ungueltig)")
    p_delete.set_defaults(func=cmd_delete)

    p_status = sub.add_parser("status", help="Detaillierter Status")
    p_status.add_argument("--name", required=True)
    p_status.set_defaults(func=cmd_status)

    p_test = sub.add_parser("test", help="SOCKS5-Test gegen Service-Adresse")
    p_test.add_argument("--name", required=True)
    p_test.set_defaults(func=cmd_test)

    p_logs = sub.add_parser("logs", help="Service-Log verfolgen")
    p_logs.add_argument("--name", required=True)
    p_logs.add_argument("--lines", type=int, default=50)
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
