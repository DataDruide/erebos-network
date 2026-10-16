"""Analysiert eine pcap und extrahiert Burst-Statistiken für Cover-Kalibrierung.

Output: JSON + menschenlesbare Zusammenfassung.
"""

import json
import sys
from pathlib import Path
from statistics import mean, median, quantiles


def load_packets(pcap_path: str) -> list:
    try:
        from scapy.all import rdpcap, TCP
    except ImportError:
        print("FEHLER: scapy nicht installiert. Bitte: pip install scapy")
        sys.exit(1)

    packets = rdpcap(pcap_path)
    frames = []
    for pkt in packets:
        if TCP in pkt:
            payload = bytes(pkt[TCP].payload)
            if len(payload) > 0:
                frames.append({
                    "time": float(pkt.time),
                    "size": len(payload),
                })
    return frames


def find_bursts(frames: list, gap_ms: float = 50.0) -> list:
    if not frames:
        return []
    bursts = []
    current = [frames[0]]
    for f in frames[1:]:
        gap = (f["time"] - current[-1]["time"]) * 1000.0
        if gap < gap_ms:
            current.append(f)
        else:
            bursts.append(current)
            current = [f]
    if current:
        bursts.append(current)
    return bursts


def safe_quantile(data, q):
    """Robustes Quantil, auch bei kleinen Stichproben."""
    if not data:
        return 0
    if len(data) < 10:
        return sorted(data)[min(len(data)-1, int(len(data) * q))]
    n = int(1 / (1 - q)) if q < 1 else 10
    try:
        return quantiles(data, n=n)[min(n-1, int(n * q) - 1)]
    except Exception:
        return sorted(data)[int(len(data) * q)]


def analyze(pcap_path: str) -> dict:
    frames = load_packets(pcap_path)
    if not frames:
        print("Keine Frames gefunden.")
        return {}

    print(f"  Frames gesamt: {len(frames)}")

    sizes = sorted(f["size"] for f in frames)
    size_stats = {
        "count": len(sizes),
        "mean": int(mean(sizes)),
        "median": int(median(sizes)),
        "p10": int(safe_quantile(sizes, 0.10)),
        "p90": int(safe_quantile(sizes, 0.90)),
        "p95": int(safe_quantile(sizes, 0.95)),
        "min": min(sizes),
        "max": max(sizes),
    }

    bursts = find_bursts(frames, gap_ms=50.0)
    burst_sizes = sorted(len(b) for b in bursts)
    burst_durations_ms = []
    inter_burst_pauses_ms = []

    for b in bursts:
        if len(b) >= 2:
            duration_ms = (b[-1]["time"] - b[0]["time"]) * 1000.0
            burst_durations_ms.append(duration_ms)

    for i in range(1, len(bursts)):
        pause_ms = (bursts[i][0]["time"] - bursts[i-1][-1]["time"]) * 1000.0
        inter_burst_pauses_ms.append(pause_ms)

    burst_stats = {
        "count": len(bursts),
        "size_mean": int(mean(burst_sizes)) if burst_sizes else 0,
        "size_median": int(median(burst_sizes)) if burst_sizes else 0,
        "size_p95": int(safe_quantile(burst_sizes, 0.95)) if burst_sizes else 0,
        "duration_mean_ms": int(mean(burst_durations_ms)) if burst_durations_ms else 0,
        "duration_median_ms": int(median(burst_durations_ms)) if burst_durations_ms else 0,
        "inter_pause_mean_ms": int(mean(inter_burst_pauses_ms)) if inter_burst_pauses_ms else 0,
        "inter_pause_median_ms": int(median(inter_burst_pauses_ms)) if inter_burst_pauses_ms else 0,
    }

    intra_gaps_ms = []
    for b in bursts:
        for i in range(1, len(b)):
            gap = (b[i]["time"] - b[i-1]["time"]) * 1000.0
            intra_gaps_ms.append(gap)

    intra_gap_stats = {
        "mean_ms": round(mean(intra_gaps_ms), 2) if intra_gaps_ms else 0,
        "median_ms": round(median(intra_gaps_ms), 2) if intra_gaps_ms else 0,
        "p10_ms": round(safe_quantile(intra_gaps_ms, 0.10), 2) if intra_gaps_ms else 0,
        "p90_ms": round(safe_quantile(intra_gaps_ms, 0.90), 2) if intra_gaps_ms else 0,
    }

    result = {
        "pcap": pcap_path,
        "frames": size_stats,
        "bursts": burst_stats,
        "intra_gap": intra_gap_stats,
    }

    print()
    print("=== Frame-Groessen ===")
    for k, v in size_stats.items():
        print(f"  {k:10} {v}")

    print()
    print("=== Burst-Metriken ===")
    for k, v in burst_stats.items():
        print(f"  {k:22} {v}")

    print()
    print("=== Intra-Burst-Abstaende (zwischen Frames im selben Burst) ===")
    for k, v in intra_gap_stats.items():
        print(f"  {k:12} {v}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_traffic.py <pcap-file>")
        sys.exit(1)
    pcap = sys.argv[1]
    result = analyze(pcap)
    out = Path.home() / "Documents/GitHub/erebos-network/traffic-stats.json"
    out.write_text(json.dumps(result, indent=2))
    print()
    print(f"JSON gespeichert: {out}")
