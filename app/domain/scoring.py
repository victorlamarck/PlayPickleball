"""Pickleball scoring rules, simplified: rally scoring to 11, win by 2, best of 3 games.

Real pickleball usually uses side-out scoring with a server number. Rally scoring keeps the
focus on the real-time architecture; swapping the rule only touches this module.

All functions are pure: they take a sequence of games and return a new list.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.errors import InvalidScoreError, InvalidStateError

Team = Literal["A", "B"]

POINTS_TO_WIN = 11
WIN_BY = 2
GAMES_TO_WIN = 2  # best of 3
MAX_GAMES = 2 * GAMES_TO_WIN - 1


@dataclass(frozen=True, slots=True)
class GameScore:
    a: int
    b: int


def game_winner(game: GameScore) -> Team | None:
    """Return the winner of a single game, or None while it is still in progress."""
    if max(game.a, game.b) >= POINTS_TO_WIN and abs(game.a - game.b) >= WIN_BY:
        return "A" if game.a > game.b else "B"
    return None


def is_match_decided(games: Sequence[GameScore]) -> Team | None:
    """Return the match winner once a team has won GAMES_TO_WIN games, else None."""
    wins = {"A": 0, "B": 0}
    for game in games:
        winner = game_winner(game)
        if winner is not None:
            wins[winner] += 1
            if wins[winner] == GAMES_TO_WIN:
                return winner
    return None


def add_point(games: Sequence[GameScore], team: Team) -> list[GameScore]:
    """Add a rally point to the current game, opening the next game when one closes."""
    if is_match_decided(games) is not None:
        raise InvalidStateError("Match is already decided")

    result = list(games)
    if not result or game_winner(result[-1]) is not None:
        result.append(GameScore(0, 0))

    current = result[-1]
    current = (
        GameScore(current.a + 1, current.b) if team == "A" else GameScore(current.a, current.b + 1)
    )
    result[-1] = current
    return _open_next_game_if_needed(result)


def set_game_score(games: Sequence[GameScore], game_index: int, a: int, b: int) -> list[GameScore]:
    """Correct the score of an existing game and return the validated game list.

    If the correction decides the match, a trailing empty (0-0) game is dropped. If it closes
    the last game without deciding the match, the next game is opened.
    """
    if not 0 <= game_index < len(games):
        raise InvalidScoreError(
            "Game index out of range", {"game_index": game_index, "games": len(games)}
        )
    corrected = GameScore(a, b)
    if not is_possible_score(corrected):
        raise InvalidScoreError("Impossible game score", {"a": a, "b": b})

    result = list(games)
    result[game_index] = corrected
    if is_match_decided(result) is not None and result[-1] == GameScore(0, 0):
        result.pop()
    validate_games(result)
    return _open_next_game_if_needed(result)


def is_possible_score(game: GameScore) -> bool:
    """True if the score can occur in a real game (in progress or exactly at the winning point)."""
    if game.a < 0 or game.b < 0:
        return False
    high, low = max(game.a, game.b), min(game.a, game.b)
    if game_winner(game) is None:
        return True
    # A finished game stops at the first winning point: 11-x (x <= 9) or deuce won by exactly 2.
    return high == max(POINTS_TO_WIN, low + WIN_BY)


def validate_games(games: Sequence[GameScore]) -> None:
    """Check that a list of games describes a reachable match state."""
    if len(games) > MAX_GAMES:
        raise InvalidScoreError("Too many games", {"games": len(games), "max": MAX_GAMES})
    for index, game in enumerate(games):
        if not is_possible_score(game):
            raise InvalidScoreError("Impossible game score", {"game_index": index})
        is_last = index == len(games) - 1
        if not is_last and game_winner(game) is None:
            raise InvalidScoreError("Only the last game can be in progress", {"game_index": index})
        if not is_last and is_match_decided(games[: index + 1]) is not None:
            raise InvalidScoreError(
                "Games recorded after the match was decided", {"game_index": index + 1}
            )


def _open_next_game_if_needed(games: list[GameScore]) -> list[GameScore]:
    if games and game_winner(games[-1]) is not None and is_match_decided(games) is None:
        games.append(GameScore(0, 0))
    return games
