# Bekannte Limitierungen

## Rendezvous-Punkt: ein Client pro Key zur Zeit

Der Rendezvous-Punkt (`peer1`) speichert pro Key **einen** Eintrag pro Rolle:

    rendezvous_pairs[key]["client"] = (reader, writer, cipher)

Bei zwei gleichzeitigen Clients mit demselben Key überschreibt der zweite
den ersten. Der erste Client verliert seine Verbindung.

**Auswirkung**: Parallele HTTP-Anfragen an denselben Hidden-Service
funktionieren nicht zuverlaessig. Ein Client zur Zeit funktioniert.

**Loesung (offen)**: `rendezvous_pairs[key]["clients"]` als Liste fuehren
und beim Weiterleiten von FRAME_DATA den richtigen Client anhand einer
Stream-ID auswaehlen. Erfordert ein Stream-ID-Feld im Frame-Format.
