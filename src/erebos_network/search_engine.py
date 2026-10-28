import os
"""Erebos Search: Durchsucht Forum, Wiki und statische Seiten."""

try:
    from sqlcipher3 import dbapi2 as sqlite3
    _SQLCIPHER = True
except ImportError:
    import sqlite3
    _SQLCIPHER = False
import logging

logger = logging.getLogger(__name__)

def search_all(query: str, db_path: str = None) -> list:
    """Durchsucht die Datenbank und gibt eine Liste von Ergebnissen zurück."""
    # Pfad dynamisch auflösen: Env-Variable -> lokaler Ordner -> Docker-Pfad
    if db_path is None:
        db_path = os.environ.get("EREBOS_DB_PATH")
    if db_path is None:
        # Suche im aktuellen Projektverzeichnis
        local_db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "forum.db")
        if os.path.isfile(local_db):
            db_path = local_db
        else:
            db_path = "/app/forum.db"  # Fallback für Docker

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
        if _SQLCIPHER:
            db_key = os.environ.get("EREBOS_DB_KEY", "")
            if db_key:
                conn.execute("PRAGMA key='" + db_key + "'")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Suche in Threads (Titel und JSON-Posts)
        cursor.execute("""
            SELECT id, title, posts FROM threads 
            WHERE title LIKE ? OR posts LIKE ?
            LIMIT 20
        """, (f"%{query}%", f"%{query}%"))
        
        threads = cursor.fetchall()
        for row in threads:
            # posts ist ein JSON-String; wir nehmen den Anfang als Snippet
            posts_raw = row["posts"]
            snippet = ""
            if posts_raw and posts_raw != "[]":
                try:
                    import json
                    posts = json.loads(posts_raw)
                    if posts and isinstance(posts, list) and len(posts) > 0:
                        first_post = posts[0]
                        body_text = first_post.get("body", "")
                        snippet = body_text[:150] + "..." if body_text else ""
                except Exception:
                    snippet = posts_raw[:150] + "..."
            
            results.append({
                "type": "Forum-Thread",
                "title": row["title"],
                "url": f"/forum/{row['id']}",
                "snippet": snippet
            })
        
        conn.close()
    except Exception as e:
        logger.error(f"Fehler bei der Datenbank-Suche: {e}")

    return results
