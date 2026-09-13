import argparse
import time

from shoppulse.db.session import health_check


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait until the ShopPulse database is healthy")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if health_check():
                print("ShopPulse PostgreSQL is healthy")
                return
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise SystemExit(f"Database did not become healthy within {args.timeout}s: {last_error}")
