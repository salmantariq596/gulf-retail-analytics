"""Create (or re-key) the github_ci Snowflake user and store its key as GitHub secrets.

    python snowflake/setup_github_ci.py --login "<YOUR ADMIN LOGIN NAME>"

The key pair is generated in memory with a random passphrase. The public key is set on
the user; the private key and passphrase go straight to `gh secret set` on stdin. Neither
is written to disk or printed. Running it again rotates the key.

Secrets created: SNOWFLAKE_ACCOUNT, SNOWFLAKE_CI_PRIVATE_KEY, SNOWFLAKE_CI_PRIVATE_KEY_PASSPHRASE.
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).parent))
from check_connection import _env  # noqa: E402
from run_sql import connect  # noqa: E402

USER = "github_ci"


def gh_secret(name: str, value: str) -> None:
    subprocess.run(["gh", "secret", "set", name], input=value, text=True, check=True,
                   stdout=subprocess.DEVNULL)
    print(f"  secret {name} set")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True, help="admin login name (the admin.p8 key's user)")
    args = ap.parse_args()

    passphrase = secrets.token_urlsafe(32)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.BestAvailableEncryption(passphrase.encode())).decode()
    public_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    public_body = "".join(line for line in public_pem.splitlines() if "-----" not in line)

    with connect("admin", "ACCOUNTADMIN", args.login) as conn:
        cur = conn.cursor()
        cur.execute(f"""create user if not exists {USER}
                        type = service default_role = transformer default_warehouse = transform_wh
                        comment = 'GitHub Actions: slim CI and deploys'""")
        cur.execute(f"grant role transformer to user {USER}")
        cur.execute(f"alter user {USER} set rsa_public_key = '{public_body}'")
    print(f"  user {USER}: created/updated, public key set")

    # prove the key works before handing it to GitHub
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    with snowflake.connector.connect(account=_env("SNOWFLAKE_ACCOUNT"), user=USER, private_key=der,
                                     role="TRANSFORMER", warehouse="TRANSFORM_WH") as conn:
        who = conn.cursor().execute("select current_user(), current_role()").fetchone()
    print(f"  login OK as {who[0]} ({who[1]})")

    gh_secret("SNOWFLAKE_ACCOUNT", _env("SNOWFLAKE_ACCOUNT"))
    gh_secret("SNOWFLAKE_CI_PRIVATE_KEY", private_pem)
    gh_secret("SNOWFLAKE_CI_PRIVATE_KEY_PASSPHRASE", passphrase)
    return 0


if __name__ == "__main__":
    sys.exit(main())
