"""Single-elimination bracket generation and advancement (pure, no I/O).

Matches are identified by (round, position): round 1 is the first round, positions are 0..n-1
within a round. The winner of (r, p) moves to (r + 1, p // 2), into slot A for even p and B for odd.
"""

from dataclasses import dataclass
from typing import Literal

from app.errors import InvalidBracketError, InvalidStateError

Slot = Literal["A", "B"]

SUPPORTED_TEAM_COUNTS = (4, 8, 16)


@dataclass(frozen=True, slots=True)
class NextMatchRef:
    round: int
    position: int
    slot: Slot


@dataclass(frozen=True, slots=True)
class MatchPlan:
    """One match in a freshly generated bracket. Seeds are only known for round 1."""

    round: int
    position: int
    seed_a: int | None
    seed_b: int | None
    next: NextMatchRef | None


@dataclass(frozen=True, slots=True)
class MatchTeams[T]:
    team_a: T | None
    team_b: T | None


def round_count(team_count: int) -> int:
    validate_team_count(team_count)
    return team_count.bit_length() - 1


def validate_team_count(team_count: int) -> None:
    if team_count not in SUPPORTED_TEAM_COUNTS:
        raise InvalidBracketError(
            "Unsupported team count",
            {"team_count": team_count, "supported": list(SUPPORTED_TEAM_COUNTS)},
        )


def seed_order(team_count: int) -> list[int]:
    """Standard bracket order, e.g. 8 -> [1, 8, 4, 5, 2, 7, 3, 6].

    Consecutive pairs are first-round matches; seeds 1 and 2 can only meet in the final.
    """
    order = [1]
    while len(order) < team_count:
        size = len(order) * 2
        order = [seed for s in order for seed in (s, size + 1 - s)]
    return order


def next_match(round_: int, position: int, total_rounds: int) -> NextMatchRef | None:
    """Where the winner of (round_, position) goes, or None for the final."""
    if round_ >= total_rounds:
        return None
    return NextMatchRef(round_ + 1, position // 2, "A" if position % 2 == 0 else "B")


def generate_bracket(team_count: int) -> list[MatchPlan]:
    """All matches of a bracket, ordered by round then position."""
    rounds = round_count(team_count)
    order = seed_order(team_count)
    plans: list[MatchPlan] = []
    for round_ in range(1, rounds + 1):
        for position in range(team_count >> round_):
            seed_a, seed_b = (
                (order[2 * position], order[2 * position + 1]) if round_ == 1 else (None, None)
            )
            plans.append(
                MatchPlan(round_, position, seed_a, seed_b, next_match(round_, position, rounds))
            )
    return plans


def place_winner[T](next_teams: MatchTeams[T], slot: Slot, winner: T) -> MatchTeams[T]:
    """Put the winner into the given slot of the next match.

    Re-placing the same team is a no-op; overwriting a different team is an error.
    """
    current = next_teams.team_a if slot == "A" else next_teams.team_b
    if current is not None and current != winner:
        raise InvalidStateError("Next match slot is already taken", {"slot": slot})
    if slot == "A":
        return MatchTeams(winner, next_teams.team_b)
    return MatchTeams(next_teams.team_a, winner)
