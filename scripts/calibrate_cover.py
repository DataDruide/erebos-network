"""Liest traffic-stats.json und schlaegt kalibrierte CoverConfig-Werte vor.

Output: menschenlesbare Tabelle + JSON mit den Werten.
"""

import json
from pathlib import Path


def main():
    stats_path = Path.home() / "Documents/GitHub/erebos-network/traffic-stats.json"
    stats = json.loads(stats_path.read_text())

    frames = stats["frames"]
    bursts = stats["bursts"]
    intra = stats["intra_gap"]

    # Kalibrierung
    # Frame-Groessen: p10 als min_size, p90 als max_size
    # (nicht p95 — sonst wird Cover selbst zu gross und auffaellig)
    min_size = max(64, frames["p10"])
    max_size = frames["p90"]

    # Burst-Groesse: Median als Default, p95 als reactive_max_match
    burst_size = bursts["size_median"]
    reactive_max_match = bursts["size_p95"]

    # Burst-Pause: Median der Pausen (in Sekunden)
    burst_pause_seconds = round(bursts["inter_pause_median_ms"] / 1000.0, 3)

    # Intra-Burst: Median der Abstaende (in Sekunden), minimum 1ms
    inter_packet_ms = max(1, int(intra["median_ms"]))

    # Reactive-Window: 2x durchschnittliche Burst-Dauer
    reactive_window_ms = max(50, int(bursts["duration_mean_ms"] * 2))

    # Reactive-Size-Jitter: IQR-aehnlich, hier p90/p50 - 1
    # (grob: Streuung der Frame-Groessen relativ zum Median)
    reactive_size_jitter = round(
        (frames["p90"] - frames["median"]) / max(1, frames["median"]),
        2,
    )
    reactive_size_jitter = max(0.1, min(0.5, reactive_size_jitter))

    proposal = {
        # Frame-Groessen
        "min_size": min_size,
        "max_size": max_size,
        # Burst-Form
        "burst_size": int(burst_size),
        "burst_pause_seconds": burst_pause_seconds,
        "inter_packet_ms": inter_packet_ms,
        # Reactive Drop-Cover
        "reactive_window_ms": reactive_window_ms,
        "reactive_max_match": int(reactive_max_match),
        "reactive_size_jitter": reactive_size_jitter,
    }

    print("=== Kalibrierungs-Vorschlag aus echten Traffic-Daten ===\n")
    print(f"  Datenquelle: {stats_path.name}")
    print(f"  Frames: {frames['count']}   Bursts: {bursts['count']}\n")

    print("--- Frame-Groessen ---")
    print(f"  min_size                   {min_size} B   (p10 der Frames)")
    print(f"  max_size                   {max_size} B   (p90 der Frames)")
    print(f"  [bisher: 256 / 1024]")
    print()

    print("--- Burst-Form ---")
    print(f"  burst_size                 {int(burst_size)}       (Median frames/burst)")
    print(f"  burst_pause_seconds        {burst_pause_seconds}     (Median inter-burst pause)")
    print(f"  inter_packet_ms            {inter_packet_ms}       (Median intra-burst gap)")
    print(f"  [bisher: 3 / 2.0 / 20]")
    print()

    print("--- Reactive Drop-Cover ---")
    print(f"  reactive_window_ms         {reactive_window_ms}     (2x mean burst duration)")
    print(f"  reactive_max_match         {int(reactive_max_match)}       (p95 frames/burst)")
    print(f"  reactive_size_jitter       {reactive_size_jitter}     (size spread)")
    print(f"  [bisher: 100 / 10 / 0.3]")
    print()

    out = Path.home() / "Documents/GitHub/erebos-network/cover-calibration.json"
    out.write_text(json.dumps(proposal, indent=2))
    print(f"JSON gespeichert: {out}")


if __name__ == "__main__":
    main()
