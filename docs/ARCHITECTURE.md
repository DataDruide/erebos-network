# Erebos — Architektur

## Überblick
Erebos ist ein 3-Hop-Onion-Netzwerk mit Post-Quantum-Kryptographie.
```mermaid
flowchart LR
    B[Browser] --> P[Lokaler Proxy]
    P --> D[Erebos-Daemon]
    D --> H1[Peer 1 Entry]
    H1 --> H2[Peer 2 Relay]
    H2 --> H3[Peer 3 Exit]
    H3 --> T[Ziel]
```
