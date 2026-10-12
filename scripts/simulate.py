"""Play a tournament through the HTTP API, round by round, so the read model changes live.

Matches of the same round are played in parallel. Each match scores `--speed` points per second.
Points carry `expected_version`; on 409 version_conflict the script takes `current_version` from
the error and retries. It can resume a half-played tournament (live matches continue, finished
ones are skipped).

Usage: uv run python scripts/simulate.py --tournament <id> [--speed 5] [--verbose]
"""

import argparse
import asyncio
import os
import random
import sys
import time
import uuid
from typing import Any

import httpx

Match = dict[str, Any]


class Simulator:
    def __init__(self, http: httpx.AsyncClient, speed: float, verbose: bool) -> None:
        self.http = http
        self.interval = 1 / speed
        self.verbose = verbose
        self.started_at = time.monotonic()
        self.points = 0
        self.conflicts = 0

    def log(self, match: Match, message: str) -> None:
        elapsed = time.monotonic() - self.started_at
        print(f"{elapsed:6.1f}s  R{match['round']}#{match['position']}  {message}", flush=True)

    async def bracket(self, tournament_id: str) -> dict[str, Any]:
        response = await self.http.get(f"/v1/tournaments/{tournament_id}/bracket")
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body

    async def run(self, tournament_id: str) -> None:
        bracket = await self.bracket(tournament_id)
        print(f"Simulating '{bracket['tournament']['name']}' ({len(bracket['rounds'])} rounds)")
        for round_index in range(len(bracket["rounds"])):
            # Re-read the bracket: winners of the previous round are now in place.
            matches = (await self.bracket(tournament_id))["rounds"][round_index]["matches"]
            print(f"--- Round {round_index + 1} ---")
            await asyncio.gather(*(self.play(m) for m in matches))

        final = (await self.bracket(tournament_id))["rounds"][-1]["matches"][0]
        champion = (
            final["team_a"] if final["winner_team_id"] == final["team_a"]["id"] else final["team_b"]
        )
        print(
            f"Champion: {champion['name']} (seed {champion['seed']}). "
            f"{self.points} points sent, {self.conflicts} version conflicts retried."
        )

    async def play(self, match: Match) -> None:
        if match["status"] == "finished":
            self.log(match, "already finished, skipping")
            return
        if match["status"] == "pending":
            match = await self.post(match, f"/v1/matches/{match['id']}/start", None)
            self.log(match, f"START  {team(match, 'a')} vs {team(match, 'b')}")

        chance_a = win_chance(match)
        while match["status"] != "finished":
            await asyncio.sleep(self.interval)
            scorer = "A" if random.random() < chance_a else "B"
            previous_games = len(match["games"])
            match = await self.point(match, scorer)
            if self.verbose:
                self.log(match, f"point {scorer}  {score(match)}  v{match['version']}")
            elif len(match["games"]) != previous_games and match["status"] != "finished":
                self.log(match, f"game   {score(match)}")

        winner = team(match, "a" if match["winner_team_id"] == match["team_a"]["id"] else "b")
        self.log(match, f"FINAL  {winner} wins  {score(match)}")

    async def point(self, match: Match, scorer: str) -> Match:
        version = match["version"]
        while True:
            body = {"team": scorer, "expected_version": version}
            response = await self.send(f"/v1/matches/{match['id']}/points", body)
            if response.status_code == 409:
                error = response.json()["error"]
                if error["code"] != "version_conflict":
                    raise RuntimeError(f"Unexpected conflict: {error}")
                self.conflicts += 1
                version = error["details"]["current_version"]
                continue
            response.raise_for_status()
            self.points += 1
            updated: Match = response.json()
            return updated

    async def post(self, match: Match, path: str, body: dict[str, Any] | None) -> Match:
        response = await self.send(path, body)
        response.raise_for_status()
        updated: Match = response.json()
        return updated

    async def send(self, path: str, body: dict[str, Any] | None) -> httpx.Response:
        """POST with an Idempotency-Key, retrying network errors with the same key."""
        key = str(uuid.uuid4())
        for attempt in range(5):
            try:
                return await self.http.post(path, json=body, headers={"Idempotency-Key": key})
            except httpx.TransportError:
                await asyncio.sleep(0.2 * 2**attempt)
        raise RuntimeError(f"API unreachable after retries: POST {path}")


def team(match: Match, side: str) -> str:
    entry = match[f"team_{side}"]
    return f"{entry['name']} ({entry['seed']})"


def score(match: Match) -> str:
    played = [g for g in match["games"] if g["a"] or g["b"]]  # hide the freshly opened 0-0 game
    return "  ".join(f"{g['a']}-{g['b']}" for g in played)


def win_chance(match: Match) -> float:
    """Slight edge for the better seed so results look plausible but upsets still happen."""
    edge = (match["team_b"]["seed"] - match["team_a"]["seed"]) * 0.015
    return float(min(0.65, max(0.35, 0.5 + edge)))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", required=True, help="Tournament id (from scripts/seed.py)")
    parser.add_argument("--speed", type=float, default=5, help="Points per second per match")
    parser.add_argument("--verbose", action="store_true", help="Log every point")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", "dev-scorekeeper-key"))
    args = parser.parse_args()
    if args.speed <= 0:
        parser.error("--speed must be positive")

    async with httpx.AsyncClient(
        base_url=args.api_url, headers={"X-API-Key": args.api_key}, timeout=10
    ) as http:
        try:
            await Simulator(http, args.speed, args.verbose).run(args.tournament)
        except (httpx.ConnectError, RuntimeError) as exc:
            print(f"{exc}\nIs the API running at {args.api_url}? (`make run`)", file=sys.stderr)
            return 1
        except httpx.HTTPStatusError as exc:
            print(f"API error: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
