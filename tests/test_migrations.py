"""Tests for idempotente Schema-Migrationen."""

import sqlite3


def test_fresh_db_has_all_columns(temp_db):
    conn = sqlite3.connect(str(temp_db))
    mail_keys_cols = {r[1] for r in conn.execute("PRAGMA table_info(mail_keys)")}
    for col in ("x25519_pub", "mlkem_pub", "x25519_priv", "mlkem_priv",
                "ed25519_pub", "ed25519_priv", "mldsa_pub", "mldsa_priv",
                "key_version", "valid_from", "revoked_at", "superseded_by"):
        assert col in mail_keys_cols, f"mail_keys.{col} fehlt"
    mailboxes_cols = {r[1] for r in conn.execute("PRAGMA table_info(mailboxes)")}
    for col in ("signature_ed25519", "signature_mldsa", "signature_mldsa_pub",
                "sender_verified", "sender_key_version", "recipient_key_version",
                "verified_at"):
        assert col in mailboxes_cols, f"mailboxes.{col} fehlt"
    hist_cols = {r[1] for r in conn.execute("PRAGMA table_info(mail_key_history)")}
    for col in ("uuid", "key_version", "x25519_pub", "mlkem_pub",
                "ed25519_pub", "mldsa_pub",
                "x25519_priv", "mlkem_priv", "ed25519_priv", "mldsa_priv",
                "valid_from", "revoked_at", "superseded_by"):
        assert col in hist_cols, f"mail_key_history.{col} fehlt"
    conn.close()


def test_migration_idempotent(temp_db):
    from erebos_network import forum_db
    conn1 = forum_db.get_db()
    conn2 = forum_db.get_db()
    assert conn1 is conn2
    forum_db._migrate_mail_keys(conn1)
    forum_db._migrate_mailboxes(conn1)
    forum_db._migrate_mail_key_history(conn1)
    forum_db._backfill_key_history_privkeys(conn1)
    cols = {r[1] for r in conn1.execute("PRAGMA table_info(mail_keys)")}
    assert "key_version" in cols


def test_mail_key_history_created_by_migration(temp_db):
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM mail_key_history").fetchone()[0]
    assert count == 0
    conn.close()


def test_key_version_default_is_null_before_migration(tmp_path, monkeypatch):
    from erebos_network import forum_db
    test_db = tmp_path / "old.db"
    monkeypatch.setattr(forum_db, "DB_PATH", test_db)
    monkeypatch.setattr(forum_db, "_conn", None)
    conn = sqlite3.connect(str(test_db))
    conn.execute("""
        CREATE TABLE mail_keys (
            uuid TEXT PRIMARY KEY,
            x25519_pub TEXT NOT NULL,
            mlkem_pub TEXT NOT NULL,
            x25519_priv TEXT NOT NULL,
            mlkem_priv TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    forum_db.get_db()
    conn = sqlite3.connect(str(test_db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(mail_keys)")}
    assert "key_version" in cols
    conn.close()
