"""Analysiert eine pcap auf Cover-Bursts.

Misst die tatsaechlichen Pausen zwischen Frames und leitet daraus
Burst-Groessen ab. Funktioniert unabhaengig von small_set/boost_factor.
"""

import json
import sys
from pathlib import Path
from statistics import mean, median

PROFILES = {
    "web":   {"burst_size": 4,  "burst_pause_ms": 108, "max_size": 7008},
    "video": {"burst_size": 10, "burst_pause_ms": 73,  "max_size": 4048},
    "api":   {"burst_size": 3,  "burst_pause_ms": 156, "max_size": 8609},
}


def load_frames(pcap_path):
    try:
        from scapy.all import rdpcap, TCP
    except ImportError:
        print("FEHLER: scapy nicht installiert")
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


def find_cover_bursts(frames, burst_pause_ms=None):
    if not frames:
        return [], 0.0

    all_gaps = []
    for i in range(1, len(frames)):
        gap_ms = (frames[i]["time"] - frames[i-1]["time"]) * 1000.0
        all_gaps.append(gap_ms)

    burst_gaps = [g for g in all_gaps if g > 10.0]

    if burst_pause_ms is None:
        burst_pause_ms = median(burst_gaps) if burst_gaps else 100.0

    print(f"  Gemessene Pausen > 10 ms: {len(burst_gaps)}")
    print(f"  Median: {burst_pause_ms:.1f} ms")

    bursts = []
    current = [frames[0]]
    for f in frames[1:]:
        gap_ms = (f["time"] - current[-1]["time"]) * 1000.0
        if gap_ms >= burst_pause_ms:
            bursts.append(current)
            current = [f]
        else:
            current.append(f)
    if current:
        bursts.append(current)
    return bursts, burst_pause_ms


def analyze_cover(pcap_path, profile_name):
    if profile_name not in PROFILES:
        print(f"FEHLER: Unbekanntes Profil: {profile_name}")
        sys.exit(1)

    cfg = PROFILES[profile_name]
    expected = cfg["burst_size"]

    print(f"=== Cover-Burst-Analyse: {pcap_path} ===")
    print(f"Profil: {profile_name}, erwartet: burst_size={expected}")

    frames = load_frames(pcap_path)
    print(f"  Frames gesamt: {len(frames)}")

    if not frames:
        return {}

    sizes = sorted(f["size"] for f in frames)
    print(f"  Frame-Median: {int(median(sizes))} B")
    print(f"  Frame-p90: {int(sizes[int(len(sizes)*0.9)])} B")

    bursts, measured_pause = find_cover_bursts(frames)
    sizes_b = [len(b) for b in bursts]

    print(f"  Bursts: {len(bursts)}")
    print(f"  Frames/Burst median: {median(sizes_b)}")
    print(f"  (erwartet: {expected})")

    if abs(median(sizes_b) - expected) <= 2:
        print("  [OK] Profil greift.")
    else:
        print(f"  [WARN] Median {median(sizes_b)} != {expected}")

    return {
        "pcap": pcap_path,
        "profile": profile_name,
        "expected_burst_size": expected,
        "measured_burst_median": median(sizes_b),
        "measured_pause_ms": measured_pause,
        "bursts": len(bursts),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyze_cover.py <pcap> <profile>")
        sys.exit(1)

    pcap = sys.argv[1]
    profile = sys.argv[2]
    result = analyze_cover(pcap, profile)

    out = Path.home() / f"Documents/GitHub/erebos-network/cover-analysis-{profile}.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nJSON gespeichert: {out}")
