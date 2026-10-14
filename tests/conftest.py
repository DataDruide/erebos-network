import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def generate_test_keys():
    keys_dir = Path(__file__).parent.parent / "erebos_keys"
    keys_dir.mkdir(exist_ok=True)

    for i in (1, 2, 3):
        pub = keys_dir / f"peer{i}_x25519.pub"
        sec = keys_dir / f"peer{i}_x25519.sec"
        if not pub.exists():
            pub.write_bytes(os.urandom(32))
        if not sec.exists():
            sec.write_bytes(os.urandom(32))

    yield
