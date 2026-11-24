"""Run a SQL file (or statements) against Snowflake with key-pair auth.

    python snowflake/run_sql.py --user admin --login "NAME@EXAMPLE.COM" --role ACCOUNTADMIN -f snowflake/01_setup.sql
    python snowflake/run_sql.py --user dbt_user --role TRANSFORMER -q "select current_role()"

--user picks the key file (~/.snowflake/keys/<user>.p8); --login overrides the Snowflake
login name when it differs from the key name. Statements run one by one and stop at the
first error; each statement's first result row is printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).parent))
from check_connection import KEY_DIR, _env  # noqa: E402


def connect(user: str, role: str, login: str | None = None):
    passphrase = _env("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = serialization.load_pem_private_key((KEY_DIR / f"{user}.p8").read_bytes(),
                                             password=passphrase.encode() if passphrase else None)
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return snowflake.connector.connect(account=_env("SNOWFLAKE_ACCOUNT"), user=login or user,
                                       private_key=der, role=role)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--login")
    ap.add_argument("--role", required=True)
    ap.add_argument("-f", "--file")
    ap.add_argument("-q", "--query", action="append", default=[])
    args = ap.parse_args()

    sql = Path(args.file).read_text(encoding="utf-8") if args.file else ";\n".join(args.query)
    with connect(args.user, args.role, args.login) as conn:
        for cur in conn.execute_string(sql, remove_comments=True):
            first = cur.fetchone() if cur.description else None
            stmt = " ".join((cur.query or "").split())[:90]
            print(f"OK  {stmt:<90} -> {first[0] if first else ''}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except snowflake.connector.errors.Error as exc:
        print(f"ERROR {type(exc).__name__}: {exc}")
        sys.exit(1)
