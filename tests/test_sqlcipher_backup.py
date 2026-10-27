"""Tests fuer SQLCipher-Backup-Roundtrip (in-process).

Prueft: Backup einer SQLCipher-DB + Restore.
"""
import sqlite3
import pytest


# Skip, wenn sqlcipher3 nicht installiert
sqlcipher = pytest.importorskip("sqlcipher3.dbapi2")


TEST_KEY = "test-key-1234567890"


def _create_sqlcipher_db(path, key, rows=3):
    conn = sqlcipher.connect(str(path))
    conn.execute("PRAGMA key='" + key + "'")
    conn.execute("PRAGMA cipher_compatibility = 4")
    conn.execute("CREATE TABLE users (username TEXT PRIMARY KEY)")
    for i in range(rows):
        conn.execute("INSERT INTO users (username) VALUES (?)", ("user" + str(i),))
    conn.commit()
    conn.close()


def _open_sqlcipher_db(path, key):
    conn = sqlcipher.connect(str(path))
    conn.execute("PRAGMA key='" + key + "'")
    conn.execute("PRAGMA cipher_compatibility = 4")
    rows = conn.execute("SELECT username FROM users ORDER BY username").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _sqlcipher_export(src, dst, key):
    conn = sqlcipher.connect(str(src))
    conn.execute("PRAGMA key='" + key + "'")
    conn.execute("PRAGMA cipher_compatibility = 4")
    conn.execute("ATTACH DATABASE '" + str(dst) + "' AS backup KEY '" + key + "'")
    conn.execute("PRAGMA backup.cipher_compatibility = 4")
    conn.execute("SELECT sqlcipher_export('backup')")
    conn.execute("DETACH DATABASE backup")
    conn.close()


def test_sqlcipher_db_is_encrypted(tmp_path):
    """SQLCipher-DB ist ohne Key nicht lesbar."""
    db = tmp_path / "enc.db"
    _create_sqlcipher_db(db, TEST_KEY)

    conn = sqlite3.connect(str(db))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("SELECT COUNT(*) FROM users").fetchone()
    conn.close()


def test_sqlcipher_backup_roundtrip(tmp_path):
    """Backup + Restore mit SQLCipher funktioniert."""
    src = tmp_path / "src.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"

    _create_sqlcipher_db(src, TEST_KEY, rows=5)
    _sqlcipher_export(src, backup, TEST_KEY)
    assert backup.exists()
    assert backup.stat().st_size > 0

    import shutil
    shutil.copy2(backup, restored)

    users = _open_sqlcipher_db(restored, TEST_KEY)
    assert len(users) == 5
    assert users == ["user0", "user1", "user2", "user3", "user4"]


def test_sqlcipher_backup_with_wrong_key_fails(tmp_path):
    """Backup mit falschem Key ist nicht lesbar."""
    src = tmp_path / "src.db"
    backup = tmp_path / "backup.db"

    _create_sqlcipher_db(src, TEST_KEY, rows=2)
    _sqlcipher_export(src, backup, TEST_KEY)

    conn = sqlcipher.connect(str(backup))
    conn.execute("PRAGMA key='wrong-key'")
    with pytest.raises(Exception):
        conn.execute("SELECT COUNT(*) FROM users").fetchone()
    conn.close()
