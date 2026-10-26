"""End-to-end roundtrip: encrypt -> save -> load -> decrypt -> verify."""

import pytest
from erebos_network.forum_db import (
    get_or_create_mail_keys, save_mail, load_mails, get_mail_keys,
    get_mail_keys_by_version, rotate_mail_keys,
)
from erebos_network.crypto.hybrid_kem import (
    encrypt_mail, decrypt_mail, sign_mail, verify_mail_with_status,
    VERIFIED, VERIFIED_OUTDATED,
)


def _full_send(owner_uuid, sender_uuid, plaintext: bytes, subject: str = "T"):
    my_keys = get_or_create_mail_keys(sender_uuid)
    recipient_keys = get_or_create_mail_keys(owner_uuid)
    encrypted = encrypt_mail(
        recipient_x25519_pub=bytes.fromhex(recipient_keys["x25519_pub"]),
        recipient_mlkem_pub=bytes.fromhex(recipient_keys["mlkem_pub"]),
        plaintext=plaintext,
    )
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(my_keys["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(my_keys["mldsa_priv"]),
        payload=plaintext,
        mldsa_pub=bytes.fromhex(my_keys["mldsa_pub"]),
    )
    save_mail(
        owner_uuid=owner_uuid, sender_uuid=sender_uuid, subject=subject,
        body="", encrypted=True,
        encrypted_fields=encrypted, signatures=sigs,
        sender_verified=False,
        sender_key_version=my_keys["key_version"],
        recipient_key_version=recipient_keys["key_version"],
    )
    return load_mails(owner_uuid)[0]


def _full_read(mail, owner_uuid):
    recipient_current = get_mail_keys(owner_uuid)
    r_version = mail["recipient_key_version"]
    decrypt_keys = (recipient_current if r_version == recipient_current["key_version"]
                    else get_mail_keys_by_version(owner_uuid, r_version))
    plaintext = decrypt_mail(
        recipient_x25519_priv=bytes.fromhex(decrypt_keys["x25519_priv"]),
        recipient_mlkem_priv=bytes.fromhex(decrypt_keys["mlkem_priv"]),
        encrypted={
            "x25519_pub": mail["x25519_pub"], "mlkem_ct": mail["mlkem_ct"],
            "nonce": mail["nonce"], "ciphertext": mail["ciphertext"],
        },
    )
    s_version = mail["sender_key_version"]
    sender_current = get_mail_keys(mail["sender_uuid"])
    version_keys = (sender_current if s_version == sender_current["key_version"]
                    else get_mail_keys_by_version(mail["sender_uuid"], s_version))
    status = verify_mail_with_status(
        ed25519_pub=bytes.fromhex(version_keys["ed25519_pub"]),
        payload=plaintext,
        signatures={
            "ed25519": mail["signature_ed25519"],
            "mldsa": mail["signature_mldsa"],
            "mldsa_pub": mail["signature_mldsa_pub"],
        },
        mldsa_pub=bytes.fromhex(version_keys["mldsa_pub"]),
        sender_key_version=s_version,
        sender_current_version=sender_current["key_version"],
    )
    return plaintext, status


def test_full_roundtrip_fresh(temp_db, uuid_a, uuid_b):
    m = _full_send(uuid_b, uuid_a, b"Hello World")
    pt, status = _full_read(m, uuid_b)
    assert pt == b"Hello World"
    assert status == VERIFIED


def test_roundtrip_after_sender_rotation(temp_db, uuid_a, uuid_b):
    _full_send(uuid_b, uuid_a, b"Before rotation")
    rotate_mail_keys(uuid_a)
    m = load_mails(uuid_b)[0]
    pt, status = _full_read(m, uuid_b)
    assert pt == b"Before rotation"
    assert status == VERIFIED_OUTDATED


def test_roundtrip_after_recipient_rotation(temp_db, uuid_a, uuid_b):
    _full_send(uuid_b, uuid_a, b"To old recipient")
    rotate_mail_keys(uuid_b)
    m = load_mails(uuid_b)[0]
    pt, status = _full_read(m, uuid_b)
    assert pt == b"To old recipient"
    assert status == VERIFIED


def test_roundtrip_after_both_rotated(temp_db, uuid_a, uuid_b):
    _full_send(uuid_b, uuid_a, b"Both rotate")
    rotate_mail_keys(uuid_a)
    rotate_mail_keys(uuid_b)
    m = load_mails(uuid_b)[0]
    pt, status = _full_read(m, uuid_b)
    assert pt == b"Both rotate"
    assert status == VERIFIED_OUTDATED


def test_tampered_ciphertext_fails_decrypt(temp_db, uuid_a, uuid_b):
    m = _full_send(uuid_b, uuid_a, b"Original")
    tampered = dict(m)
    tampered["ciphertext"] = "00" * (len(m["ciphertext"]) // 2)
    keys = get_mail_keys(uuid_b)
    with pytest.raises(Exception):
        decrypt_mail(
            recipient_x25519_priv=bytes.fromhex(keys["x25519_priv"]),
            recipient_mlkem_priv=bytes.fromhex(keys["mlkem_priv"]),
            encrypted={
                "x25519_pub": tampered["x25519_pub"],
                "mlkem_ct": tampered["mlkem_ct"],
                "nonce": tampered["nonce"],
                "ciphertext": tampered["ciphertext"],
            },
        )
