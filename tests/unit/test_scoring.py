import pytest

from app.domain.scoring import (
    GameScore,
    Team,
    add_point,
    game_winner,
    is_match_decided,
    is_possible_score,
    set_game_score,
    validate_games,
)
from app.errors import InvalidScoreError, InvalidStateError


def play(points: str, games: list[GameScore] | None = None) -> list[GameScore]:
    """Apply a string of rally winners, e.g. "AAB" -> A, A, B."""
    result = list(games or [])
    for team in points:
        assert team in ("A", "B")
        t: Team = "A" if team == "A" else "B"
        result = add_point(result, t)
    return result


G = GameScore


class TestGameWinner:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            (0, 0, None),
            (10, 9, None),
            (11, 9, "A"),
            (9, 11, "B"),
            (11, 0, "A"),
            (11, 10, None),  # deuce: must win by 2
            (12, 10, "A"),
            (14, 16, "B"),
            (15, 15, None),
        ],
    )
    def test_game_winner(self, a: int, b: int, expected: Team | None) -> None:
        assert game_winner(G(a, b)) == expected


class TestAddPoint:
    def test_first_point_opens_first_game(self) -> None:
        assert add_point([], "A") == [G(1, 0)]
        assert add_point([], "B") == [G(0, 1)]

    def test_does_not_mutate_input(self) -> None:
        games = [G(3, 2)]
        add_point(games, "A")
        assert games == [G(3, 2)]

    def test_win_11_9_opens_next_game(self) -> None:
        games = play("A" * 9 + "B" * 9 + "AA")
        assert games == [G(11, 9), G(0, 0)]

    def test_deuce_continues_at_11_10_and_ends_at_12_10(self) -> None:
        games = play("A" * 10 + "B" * 10 + "A")
        assert games == [G(11, 10)]
        games = add_point(games, "A")
        assert games == [G(12, 10), G(0, 0)]

    def test_extended_deuce(self) -> None:
        games = play("AB" * 14 + "BB")
        assert games == [G(14, 16), G(0, 0)]

    def test_match_decided_in_two_games(self) -> None:
        games = play("A" * 11 + "A" * 11)
        assert games == [G(11, 0), G(11, 0)]
        assert is_match_decided(games) == "A"

    def test_match_decided_in_three_games(self) -> None:
        games = play("A" * 11 + "B" * 11 + "B" * 11)
        assert games == [G(11, 0), G(0, 11), G(0, 11)]
        assert is_match_decided(games) == "B"

    def test_point_after_match_decided_raises(self) -> None:
        games = play("A" * 22)
        with pytest.raises(InvalidStateError):
            add_point(games, "B")

    def test_opens_new_game_if_last_one_is_finished(self) -> None:
        # Can happen after a correction closed the last game of a list without an open game.
        assert add_point([G(11, 3)], "B") == [G(11, 3), G(0, 1)]


class TestIsMatchDecided:
    @pytest.mark.parametrize(
        ("games", "expected"),
        [
            ([], None),
            ([G(5, 3)], None),
            ([G(11, 3), G(0, 0)], None),
            ([G(11, 3), G(3, 11), G(10, 10)], None),
            ([G(11, 3), G(11, 5)], "A"),
            ([G(3, 11), G(11, 9), G(10, 12)], "B"),
        ],
    )
    def test_is_match_decided(self, games: list[GameScore], expected: Team | None) -> None:
        assert is_match_decided(games) == expected


class TestIsPossibleScore:
    @pytest.mark.parametrize(
        "game",
        [G(0, 0), G(10, 10), G(11, 10), G(20, 19), G(11, 9), G(11, 0), G(12, 10), G(9, 11)],
    )
    def test_possible(self, game: GameScore) -> None:
        assert is_possible_score(game)

    @pytest.mark.parametrize("game", [G(-1, 0), G(0, -3), G(15, 3), G(12, 9), G(13, 10), G(14, 0)])
    def test_impossible(self, game: GameScore) -> None:
        assert not is_possible_score(game)


class TestSetGameScore:
    def test_correct_current_game(self) -> None:
        assert set_game_score([G(5, 3)], 0, 4, 3) == [G(4, 3)]

    def test_correct_finished_game_keeps_winner(self) -> None:
        assert set_game_score([G(11, 9), G(2, 1)], 0, 11, 7) == [G(11, 7), G(2, 1)]

    def test_correction_that_closes_last_game_opens_next(self) -> None:
        assert set_game_score([G(10, 9)], 0, 11, 9) == [G(11, 9), G(0, 0)]

    def test_correction_that_decides_match_drops_empty_game(self) -> None:
        games = [G(11, 5), G(9, 11), G(0, 0)]
        assert set_game_score(games, 1, 11, 9) == [G(11, 5), G(11, 9)]

    def test_correction_that_decides_match_with_scored_game_after_is_rejected(self) -> None:
        games = [G(11, 5), G(9, 11), G(3, 2)]
        with pytest.raises(InvalidScoreError):
            set_game_score(games, 1, 11, 9)

    def test_reopening_a_closed_game_that_is_not_last_is_rejected(self) -> None:
        with pytest.raises(InvalidScoreError):
            set_game_score([G(11, 5), G(3, 2)], 0, 10, 5)

    @pytest.mark.parametrize(("a", "b"), [(-1, 3), (15, 3), (13, 10)])
    def test_impossible_scores_rejected(self, a: int, b: int) -> None:
        with pytest.raises(InvalidScoreError):
            set_game_score([G(5, 3)], 0, a, b)

    @pytest.mark.parametrize("index", [-1, 1, 5])
    def test_index_out_of_range(self, index: int) -> None:
        with pytest.raises(InvalidScoreError):
            set_game_score([G(5, 3)], index, 1, 1)

    def test_error_details_are_populated(self) -> None:
        with pytest.raises(InvalidScoreError) as exc_info:
            set_game_score([G(5, 3)], 0, 15, 3)
        assert exc_info.value.details == {"a": 15, "b": 3}


class TestValidateGames:
    def test_valid_states(self) -> None:
        validate_games([])
        validate_games([G(11, 5), G(3, 11), G(7, 7)])

    def test_impossible_game_rejected(self) -> None:
        with pytest.raises(InvalidScoreError):
            validate_games([G(15, 3)])

    def test_too_many_games(self) -> None:
        with pytest.raises(InvalidScoreError):
            validate_games([G(11, 5), G(5, 11), G(11, 5), G(0, 0)])
