"""Credential and token-cache helpers shared by the MCP server and the
interactive setup script.

The Garmin login email is not secret and is kept in a small JSON file.
The Garmin password is kept out of any file entirely and is stored in
the macOS keychain (visible in Keychain Access / iCloud Keychain as the
"garmin-mcp" item), retrieved on demand via the `security` CLI.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

APP_DIR = Path.home() / ".garmin_mcp"
TOKEN_DIR = APP_DIR / "tokens"
CONFIG_PATH = APP_DIR / "config.json"
KEYCHAIN_SERVICE = "garmin-mcp"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(mode=0o700, exist_ok=True)
    TOKEN_DIR.mkdir(mode=0o700, exist_ok=True)


def load_email() -> str | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("email")


def save_email(email: str) -> None:
    ensure_app_dir()
    CONFIG_PATH.write_text(json.dumps({"email": email}))
    CONFIG_PATH.chmod(0o600)


def get_password(email: str) -> str | None:
    """Read the Garmin password for `email` from the macOS keychain.

    Returns None if no matching keychain item exists.
    """
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            email,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def set_password(email: str, password: str) -> None:
    """Store/update the Garmin password for `email` in the macOS keychain.

    Note: the password is passed as a CLI argument to `security`, so it is
    briefly visible to other processes on the same machine via `ps` for the
    lifetime of that single command. This is a known limitation of the
    `security` CLI (it has no stdin-based way to set a password) and is an
    acceptable tradeoff on a single-user machine; the value is never written
    to disk or shell history.
    """
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            email,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            password,
            "-U",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def tokenstore_path() -> str:
    ensure_app_dir()
    return str(TOKEN_DIR)
