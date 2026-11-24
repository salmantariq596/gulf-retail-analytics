"""Generate RSA key pairs for Snowflake key-pair authentication.

    python snowflake/generate_keypair.py dlt_user dbt_user lightdash_user

Writes encrypted private keys to ~/.snowflake/keys/<user>.p8 (outside the repo)
and prints the ALTER USER statements to paste into snowflake/01_setup.sql.
The passphrase is read from SNOWFLAKE_PRIVATE_KEY_PASSPHRASE (prompted if unset).
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_DIR = Path.home() / ".snowflake" / "keys"


def main(users: list[str]) -> None:
    if not users:
        sys.exit(__doc__)
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or getpass.getpass("Passphrase for the private keys: ")
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    for user in users:
        path = KEY_DIR / f"{user}.p8"
        if path.exists():
            print(f"-- {path} exists, skipping {user} (delete it to rotate)")
            continue
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode()),
        ))
        try:
            path.chmod(0o600)
        except OSError:
            pass
        public = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        body = "".join(line for line in public.splitlines() if "-----" not in line)
        print(f"-- private key: {path}")
        print(f"alter user {user} set rsa_public_key = '{body}';\n")


if __name__ == "__main__":
    main(sys.argv[1:])
