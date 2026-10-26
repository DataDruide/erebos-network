"""Tests for _migrate_incomplete_mail_keys (Lazy-Migration)."""

import sqlite3


def _insert_incomplete_uuid(temp_db, uuid):
    conn = sqlite3.connect(str(temp_db))
    conn.execute("""
        INSERT INTO mail_keys
            (uuid, x25519_pub, mlkem_pub, x25519_priv, mlkem_priv,
             ed25519_pub, ed25519_priv, mldsa_pub, mldsa_priv,
             key_version, valid_from, created_at)
        VALUES (?, 'aa', 'bb', 'cc', 'dd', NULL, NULL, NULL, NULL,
                1, 1000.0, 1000.0)
    """, (uuid,))
    conn.commit()
    conn.close()


def _get_mail_keys_row(temp_db, uuid):
    conn = sqlite3.connect(str(temp_db))
    row = conn.execute(
        "SELECT ed25519_pub, ed25519_priv, mldsa_pub, mldsa_priv, key_version "
        "FROM mail_keys WHERE uuid = ?", (uuid,),
    ).fetchone()
    conn.close()
    return row


def test_incomplete_uuid_is_migrated(temp_db):
    from erebos_network import forum_db
    uuid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    _insert_incomplete_uuid(temp_db, uuid)
    row = _get_mail_keys_row(temp_db, uuid)
    assert row[0] is None
    forum_db.get_db()
    row = _get_mail_keys_row(temp_db, uuid)
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
    assert len(row[0]) == 64
    assert len(row[2]) == 3904


def test_complete_uuid_unchanged(temp_db):
    from erebos_network import forum_db
    from erebos_network.forum_db import get_or_create_mail_keys
    uuid = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    keys_before = get_or_create_mail_keys(uuid)
    ed_pub_before = keys_before["ed25519_pub"]
    forum_db.get_db()
    row = _get_mail_keys_row(temp_db, uuid)
    assert row[0] == ed_pub_before


def test_migration_idempotent(temp_db):
    from erebos_network import forum_db
    uuid = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    _insert_incomplete_uuid(temp_db, uuid)
    forum_db.get_db()
    row1 = _get_mail_keys_row(temp_db, uuid)
    forum_db.get_db()
    row2 = _get_mail_keys_row(temp_db, uuid)
    assert row1 == row2


def test_migration_creates_history_entry(temp_db):
    from erebos_network import forum_db
    uuid = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    _insert_incomplete_uuid(temp_db, uuid)
    forum_db.get_db()
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM mail_key_history WHERE uuid = ?", (uuid,),
    ).fetchone()[0]
    conn.close()
    assert count >= 1
