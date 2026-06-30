#!/usr/bin/env python3

import argparse

from polymarket_template_utils import (
    clob_client,
    credential_fields,
    load_env_files,
    masked,
    print_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive Polymarket CLOB API credentials from PRIVATE_KEY.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of shell export lines.")
    parser.add_argument(
        "--show-secret",
        action="store_true",
        help="Print full API secret/passphrase values. Use only in a private terminal.",
    )
    args = parser.parse_args()

    load_env_files()
    client = clob_client(require_creds=False)
    credentials = client.create_or_derive_api_key()
    fields = credential_fields(credentials)

    if not args.show_secret:
        fields = {key: (value if key == "CLOB_API_KEY" else masked(value)) for key, value in fields.items()}

    if args.json:
        print_json(fields)
        return

    if not args.show_secret:
        print("# Secrets are masked. Re-run with --show-secret in a private terminal to print usable exports.")
    for key, value in fields.items():
        print(f"export {key}='{value}'")


if __name__ == "__main__":
    main()
