from __future__ import annotations

import time


def main() -> None:
    print("Motis worker configured. Waiting for database-backed jobs.", flush=True)
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
