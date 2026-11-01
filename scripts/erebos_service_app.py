#!/usr/bin/env python3
"""
Erebos Service App (Lokal, Dezentral)
Ein GUI-Tool, mit dem jeder Nutzer seinen eigenen Hidden Service starten kann.
"""

import tkinter as tk
from tkinter import messagebox, ttk
import threading
import asyncio
import logging
import time
import http.server
import socketserver
import os
import secrets

from erebos_network.hidden_service_runtime import HiddenServiceRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ErebosServiceApp")


class ServiceRunner:
    """Kapselt die asyncio-Loop, die Runtime und den lokalen HTTP-Server."""
    def __init__(self, config: dict):
        self.config = config
        self.runtime = None
        self.loop = None
        self.thread = None
        self.http_server = None
        self.http_thread = None
        self._ready = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=10)

    def _run_loop(self):
        # 1. Lokalen HTTP-Server starten
        self._start_http_server()

        # 2. Erebos-Runtime starten
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.runtime = HiddenServiceRuntime(
            rendezvous_host=self.config.get("rendezvous_host", "127.0.0.1"),
            rendezvous_port=self.config.get("rendezvous_port", 9999),
            http_backend_host=self.config.get("http_backend_host", "127.0.0.1"),
            http_backend_port=self.config.get("http_backend_port", 8080),
            intro_points=self.config.get("intro_points"),
            dht_peers=self.config.get("dht_peers"),
            bind_port=self.config.get("bind_port", 9080),
        )
        try:
            self.loop.run_until_complete(self.runtime.run())
        except Exception as e:
            logger.error(f"Runtime-Fehler: {e}")

    def _start_http_server(self):
        port = self.config.get("http_backend_port", 8080)
        class SimpleHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # Keine Log-Spam in der Konsole
        
        try:
            self.http_server = socketserver.TCPServer(("", port), SimpleHandler)
            self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_thread.start()
            logger.info(f"Lokaler HTTP-Server gestartet auf Port {port}")
        except OSError as e:
            logger.error(f"HTTP-Server konnte nicht auf Port {port} starten: {e}")

    def stop(self):
        if self.http_server:
            self.http_server.shutdown()
            self.http_server.server_close()
        if self.runtime:
            self.runtime.stop()

    def get_address(self):
        if self.runtime:
            return self.runtime.address
        return None


class ErebosServiceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Erebos Service Manager")
        self.root.geometry("700x600")
        self.root.configure(bg="#050508")

        self.runners = []
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0d1117")
        style.configure("TLabel", background="#0d1117", foreground="#e6edf3", font=("Helvetica", 12))
        style.configure("TButton", background="#21262d", foreground="#e6edf3", font=("Helvetica", 11))
        style.map("TButton", background=[("active", "#da3633")])
        style.configure("Treeview", background="#0d1117", foreground="#e6edf3", fieldbackground="#0d1117")
        style.configure("Treeview.Heading", background="#21262d", foreground="#ff3333", font=("Helvetica", 11, "bold"))

        header = ttk.Label(self.root, text="EREBOS SERVICE MANAGER", font=("Helvetica", 16, "bold"), foreground="#ff3333")
        header.pack(pady=20)

        config_frame = ttk.Frame(self.root)
        config_frame.pack(pady=10, padx=20, fill="x")

        ttk.Label(config_frame, text="Lokaler Port:").pack(side="left", padx=5)
        self.port_entry = ttk.Entry(config_frame, width=8)
        self.port_entry.pack(side="left", padx=5)
        self.port_entry.insert(0, "8080")

        ttk.Label(config_frame, text="Rendezvous-Host:").pack(side="left", padx=5)
        self.rendezvous_entry = ttk.Entry(config_frame, width=15)
        self.rendezvous_entry.pack(side="left", padx=5)
        self.rendezvous_entry.insert(0, "127.0.0.1")

        start_btn = ttk.Button(config_frame, text="Dienst starten", command=self.start_service)
        start_btn.pack(side="left", padx=20)

        stop_btn = ttk.Button(config_frame, text="Stoppen", command=self.stop_service)
        stop_btn.pack(side="left", padx=5)

        self.info_label = ttk.Label(self.root, text="Bereit. Gib einen Port ein und starte den Dienst.", foreground="#8b949e")
        self.info_label.pack(pady=10)

        list_frame = ttk.Frame(self.root)
        list_frame.pack(pady=10, padx=20, fill="both", expand=True)

        columns = ("port", "address", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        self.tree.heading("port", text="Port")
        self.tree.heading("address", text=".erebos Adresse")
        self.tree.heading("status", text="Status")
        self.tree.column("port", width=60)
        self.tree.column("address", width=400)
        self.tree.column("status", width=80)
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Label(self.root, text="Dezentral. Deine Schluessel bleiben lokal.", foreground="#8b949e", font=("Helvetica", 10))
        footer.pack(pady=10)

    def stop_service(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Bitte wähle einen Dienst aus der Liste aus.")
            return
        
        item = selected[0]
        values = self.tree.item(item, "values")
        port = int(values[0])
        
        for runner in self.runners:
            if runner.config["http_backend_port"] == port:
                runner.stop()
                self.runners.remove(runner)
                break
        
        self.tree.delete(item)
        self.info_label.config(text=f"Dienst auf Port {port} gestoppt.", foreground="#8b949e")

    def start_service(self):
        port_str = self.port_entry.get().strip()
        if not port_str.isdigit():
            messagebox.showerror("Fehler", "Bitte gib eine gueltige Portnummer ein.")
            return
        port = int(port_str)

        for runner in self.runners:
            if runner.config["http_backend_port"] == port:
                messagebox.showerror("Fehler", "Dieser Port ist bereits belegt.")
                return

        self.info_label.config(text=f"Starte Dienst auf Port {port}...", foreground="#fbbf24")
        self.root.update()

        config = {
            "bind_port": port + 1001,  # Runtime nutzt einen anderen Port (z.B. 9081)
            "http_backend_port": port,  # Unser HTTP-Server nutzt den eingegebenen Port (z.B. 8080)
            "rendezvous_host": self.rendezvous_entry.get().strip(),
            "rendezvous_port": 9999,
        }

        runner = ServiceRunner(config)
        runner.start()
        self.runners.append(runner)

        for _ in range(50):
            addr = runner.get_address()
            if addr:
                break
            time.sleep(0.1)

        addr = runner.get_address()
        if addr:
            self.tree.insert("", "end", values=(port, addr, "Aktiv"))
            self.info_label.config(text=f"Dienst laeuft: {addr}", foreground="#00ff88")
        else:
            self.tree.insert("", "end", values=(port, "Fehler", "Timeout"))
            self.info_label.config(text="Fehler: Adresse nicht generiert.", foreground="#ff3333")


if __name__ == "__main__":
    # EREBOS_DB_KEY setzen (falls nicht gesetzt)
    # Jeder Dienst bekommt einen eigenen Schlüssel (isoliert)
    if "EREBOS_DB_KEY" not in os.environ:
        os.environ["EREBOS_DB_KEY"] = secrets.token_hex(32)
        logging.info("EREBOS_DB_KEY generiert (64 Hex-Zeichen)")
    
    root = tk.Tk()
    app = ErebosServiceApp(root)
    root.mainloop()
