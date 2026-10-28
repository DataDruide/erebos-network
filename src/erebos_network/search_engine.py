"""Erebos Search: Durchsucht Forum, Wiki und statische Seiten."""

import sqlite3
import logging

logger = logging.getLogger(__name__)

def search_all(query: str, db_path: str = "/app/forum.db") -> list:
    """Durchsucht die Datenbank und gibt eine Liste von Ergebnissen zurück."""
    results = []
    if not query:
        return results

    query_lower = query.lower()

    # 1. Statische Seiten (Hardcodiert, da sie im Code liegen)
    static_pages = [
        {"title": "Hidden Wiki", "url": "/wiki", "snippet": "Eine Liste der verfuegbaren Dienste im Erebos-Netzwerk."},
        {"title": "Erebos Forum", "url": "/forum", "snippet": "Diskutiere mit anderen Nutzern im Darknet."},
        {"title": "Anonymes Postfach", "url": "/mail", "snippet": "Sichere Nachrichten empfangen und senden."},
        {"title": "Erebos Chat", "url": "/chat", "snippet": "Echtzeit-Kommunikation im Darknet."},
        {"title": "Regeln & Richtlinien", "url": "/rules", "snippet": "Die Regeln des Erebos-Netzwerks."},
    ]

    for page in static_pages:
        if query_lower in page["title"].lower() or query_lower in page["snippet"].lower():
            results.append({
                "type": "Seite",
                "title": page["title"],
                "url": page["url"],
                "snippet": page["snippet"]
            })

    # 2. Forum-Threads (aus der Datenbank)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Suche in Threads (Titel und Inhalt)
        cursor.execute("""
            SELECT id, title, body FROM threads 
            WHERE title LIKE ? OR body LIKE ?
            LIMIT 20
        """, (f"%{query}%", f"%{query}%"))
        
        threads = cursor.fetchall()
        for row in threads:
            results.append({
                "type": "Forum-Thread",
                "title": row["title"],
                "url": f"/forum/{row['id']}",
                "snippet": row["body"][:150] + "..." if row["body"] else ""
            })
        
        conn.close()
    except Exception as e:
        logger.error(f"Fehler bei der Datenbank-Suche: {e}")

    return results
