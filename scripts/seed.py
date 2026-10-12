"""Create the "Demo Open" 8-team tournament through the HTTP API.

Usage: uv run python scripts/seed.py [--api-url http://localhost:8000]
"""

import argparse
import os
import sys

import httpx

TEAMS = [
    "Dink Dynasty",
    "Kitchen Kings",
    "Third Shot Drop",
    "Erne Express",
    "Lob City",
    "Net Ninjas",
    "Paddle Pirates",
    "Spin Doctors",
]
EMULATOR_UI = "http://localhost:4000/firestore/default/data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", "dev-scorekeeper-key"))
    parser.add_argument("--name", default="Demo Open")
    args = parser.parse_args()

    try:
        response = httpx.post(
            f"{args.api_url}/v1/tournaments",
            json={"name": args.name, "teams": [{"name": team} for team in TEAMS]},
            headers={"X-API-Key": args.api_key},
            timeout=10,
        )
    except httpx.ConnectError:
        print(f"Cannot reach the API at {args.api_url}. Is `make run` running?", file=sys.stderr)
        return 1
    if response.status_code != 201:
        print(f"Failed: {response.status_code} {response.text}", file=sys.stderr)
        return 1

    tournament = response.json()
    tournament_id = tournament["id"]
    print(f"Created tournament '{tournament['name']}' with {len(TEAMS)} teams")
    print(f"  tournament id : {tournament_id}")
    print(f"  bracket (API) : {args.api_url}/v1/tournaments/{tournament_id}/bracket")
    print(f"  Firestore UI  : {EMULATOR_UI}/tournaments/{tournament_id}")
    print()
    print("Next:")
    print(f'  make simulate ARGS="--tournament {tournament_id} --speed 5"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
