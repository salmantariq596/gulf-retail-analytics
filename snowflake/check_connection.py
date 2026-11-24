"""Check key-pair logins and role scoping for the service users.

    python snowflake/check_connection.py

For each user: logs in with its private key and prints its role, warehouse and the
databases it can see - which should match the least-privilege design:
    dlt_user        LOADER       RAW
    dbt_user        TRANSFORMER  RAW, DEV, PROD
    lightdash_user  REPORTER     PROD
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

KEY_DIR = Path.home() / ".snowflake" / "keys"
USERS = {"dlt_user": "LOADER", "dbt_user": "TRANSFORMER", "lightdash_user": "REPORTER"}


def _env(name: str) -> str | None:
    """Process env first, then the Windows user env (set without restarting the shell)."""
    value = os.getenv(name)
    if value is None and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = winreg.QueryValueEx(key, name)[0]
        except OSError:
            value = None
    return value


def main() -> int:
    account = _env("SNOWFLAKE_ACCOUNT")
    passphrase = _env("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    if not account:
        print("SNOWFLAKE_ACCOUNT is not set")
        return 1
    ok = True
    for user, role in USERS.items():
        key_pem = (KEY_DIR / f"{user}.p8").read_bytes()
        key = serialization.load_pem_private_key(key_pem, password=passphrase.encode() if passphrase else None)
        der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        try:
            with snowflake.connector.connect(account=account, user=user, private_key=der, role=role) as conn:
                cur = conn.cursor()
                cur.execute("select current_user(), current_role(), current_warehouse()")
                who = cur.fetchone()
                cur.execute("show databases")
                dbs = sorted(r[1] for r in cur.fetchall() if r[1] not in ("SNOWFLAKE", "SNOWFLAKE_SAMPLE_DATA"))
                print(f"OK    {who[0]:<15} role={who[1]:<12} warehouse={who[2]:<13} databases={dbs}")
        except Exception as exc:  # noqa: BLE001 - report every user, then fail
            ok = False
            print(f"FAIL  {user:<15} {type(exc).__name__}: {str(exc).splitlines()[0]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
