"""Tests for sender_verified-Persistenz + verified_at."""

from erebos_network.forum_db import save_mail, load_mails, set_mail_verified


def _make_mail(uuid_a, uuid_b):
    save_mail(
        owner_uuid=uuid_b, sender_uuid=uuid_a, subject="Test",
        body="", encrypted=False,
        sender_key_version=1, recipient_key_version=1,
    )
    mails = load_mails(uuid_b)
    assert len(mails) == 1
    return mails[0]


def test_save_and_load_mail(temp_db, uuid_a, uuid_b):
    save_mail(
        owner_uuid=uuid_b, sender_uuid=uuid_a, subject="Hi",
        body="", encrypted=False,
        sender_key_version=1, recipient_key_version=1,
    )
    mails = load_mails(uuid_b)
    assert len(mails) == 1
    assert mails[0]["subject"] == "Hi"
    assert mails[0]["sender_verified"] == 0
    assert mails[0]["verified_at"] is None


def test_set_mail_verified_persists(temp_db, uuid_a, uuid_b):
    m = _make_mail(uuid_a, uuid_b)
    set_mail_verified(m["id"], 2)
    mails = load_mails(uuid_b)
    assert mails[0]["sender_verified"] == 2
    assert mails[0]["verified_at"] is not None


def test_persisted_status_not_overwritten_by_repeated_set(temp_db, uuid_a, uuid_b):
    m = _make_mail(uuid_a, uuid_b)
    set_mail_verified(m["id"], 1)
    first_at = load_mails(uuid_b)[0]["verified_at"]
    import time as _t
    _t.sleep(0.01)
    set_mail_verified(m["id"], 1)
    mails = load_mails(uuid_b)
    assert mails[0]["sender_verified"] == 1
    assert mails[0]["verified_at"] >= first_at


def test_sender_verified_is_int_not_bool(temp_db, uuid_a, uuid_b):
    m = _make_mail(uuid_a, uuid_b)
    set_mail_verified(m["id"], 2)
    val = load_mails(uuid_b)[0]["sender_verified"]
    assert isinstance(val, int)
    assert not isinstance(val, bool)
    assert val == 2
