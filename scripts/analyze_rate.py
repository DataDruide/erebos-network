"""Zaehlt Frames pro Sekunde in einer pcap."""

import sys
from collections import Counter

try:
    from scapy.all import rdpcap, TCP
except ImportError:
    print("FEHLER: scapy nicht installiert")
    sys.exit(1)

pcap = sys.argv[1]
packets = rdpcap(pcap)

# Frames pro Sekunde (gerundet)
per_second = Counter()
frames = []
for pkt in packets:
    if TCP in pkt:
        payload = bytes(pkt[TCP].payload)
        if len(payload) > 0:
            t = float(pkt.time)
            per_second[int(t)] += 1
            frames.append((t, len(payload)))

if not frames:
    print("Keine Frames gefunden.")
    sys.exit(0)

print(f"Frames gesamt: {len(frames)}")
print(f"Zeitspanne: {frames[-1][0] - frames[0][0]:.2f} s")
print(f"Durchschnitt: {len(frames) / (frames[-1][0] - frames[0][0]):.0f} Frames/s")
print()
print("Frames pro Sekunde:")
for sec in sorted(per_second):
    print(f"  {sec}: {per_second[sec]} Frames")
