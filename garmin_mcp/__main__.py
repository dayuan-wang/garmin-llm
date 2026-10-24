"""Entry point: python -m garmin_mcp [--demo | auth]."""

import argparse
import getpass
import os

from .garmin import KEY_FILE


def save_key():
    # Local terminal input only. This is not an MCP tool and never reaches a model.
    if KEY_FILE.exists():
        raise SystemExit(f"Key file already exists at {KEY_FILE}; remove it yourself before replacing it.")
    key = getpass.getpass("Garmin Personal API key (hidden): ").strip()
    if not key or "\n" in key or "\r" in key:
        raise SystemExit("Empty or invalid key; nothing saved.")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(key)
    print(f"Key saved locally to {KEY_FILE}. Not yet validated with Garmin.")


def main():
    parser = argparse.ArgumentParser(description="Garmin Learning MCP: health data, analysis and local training journal")
    parser.add_argument("command", nargs="?", choices=["auth"])
    parser.add_argument("--demo", action="store_true", help="Use clearly labeled synthetic data; no network or key")
    args = parser.parse_args()
    if args.command == "auth":
        if args.demo:
            parser.error("auth and --demo cannot be combined")
        save_key()
    else:
        from .server import create_server
        # stdout is the JSON-RPC wire. Send diagnostics to stderr, never print here.
        create_server(demo=args.demo).run(transport="stdio")


if __name__ == "__main__":
    main()
