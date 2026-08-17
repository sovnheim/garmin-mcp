#!/usr/bin/env python3
"""One-time (or occasional) interactive Garmin Connect login.

Run this manually from a terminal (not from Claude Desktop):

    uv run python scripts/setup_auth.py

It logs in to Garmin Connect, prompting for your MFA code if Garmin asks
for one, and caches the resulting session token to ~/.garmin_mcp/tokens.
The garmin_mcp MCP server then reuses/refreshes that cached token headlessly
and never needs to prompt for MFA itself.

Your Garmin password is stored in the macOS keychain (item "garmin-mcp"),
never in a file. Re-run this script whenever a tool call reports a Garmin
session/auth error (the cached refresh token has expired or was revoked).
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from garminconnect import (  # noqa: E402
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

from garmin_mcp import auth  # noqa: E402


def prompt_mfa() -> str:
    return input("Enter the Garmin MFA / one-time code: ").strip()


def main() -> int:
    auth.ensure_app_dir()

    saved_email = auth.load_email()
    prompt = f"Garmin Connect email [{saved_email}]: " if saved_email else "Garmin Connect email: "
    email = input(prompt).strip() or saved_email
    if not email:
        print("An email address is required.", file=sys.stderr)
        return 1

    existing_password = auth.get_password(email)
    if existing_password:
        reuse = input(
            "A password for this account is already stored in the keychain. "
            "Reuse it? [Y/n]: "
        ).strip().lower()
        password = existing_password if reuse in ("", "y", "yes") else None
    else:
        password = None

    if password is None:
        password = getpass.getpass(f"Garmin Connect password for {email}: ")
        if not password:
            print("A password is required.", file=sys.stderr)
            return 1
        auth.set_password(email, password)
        print("Password stored in the macOS keychain (service: garmin-mcp).")

    client = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)

    print("Logging in to Garmin Connect...")
    try:
        mfa_status, _legacy_token = client.login(tokenstore=auth.tokenstore_path())
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    if mfa_status:
        print(
            "Login did not complete (Garmin still reports MFA required). "
            "Please re-run this script.",
            file=sys.stderr,
        )
        return 1

    auth.save_email(email)
    print(f"Success. Session token cached at {auth.tokenstore_path()}")
    print("You can now use the garmin_mcp server from Claude Desktop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
