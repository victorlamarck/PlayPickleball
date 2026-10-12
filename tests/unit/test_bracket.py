import pytest

from app.domain.bracket import (
    MatchTeams,
    NextMatchRef,
    generate_bracket,
    next_match,
    place_winner,
    round_count,
    seed_order,
)
from app.errors import InvalidBracketError, InvalidStateError


class TestSeedOrder:
    def test_four_teams(self) -> None:
        assert seed_order(4) == [1, 4, 2, 3]

    def test_eight_teams(self) -> None:
        assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]

    def test_sixteen_teams(self) -> None:
        assert seed_order(16) == [1, 16, 8, 9, 4, 13, 5, 12, 2, 15, 7, 10, 3, 14, 6, 11]

    @pytest.mark.parametrize("n", [4, 8, 16])
    def test_each_pair_sums_to_n_plus_1(self, n: int) -> None:
        order = seed_order(n)
        assert sorted(order) == list(range(1, n + 1))
        assert all(order[i] + order[i + 1] == n + 1 for i in range(0, n, 2))


class TestGenerateBracket:
    @pytest.mark.parametrize(("n", "rounds"), [(4, 2), (8, 3), (16, 4)])
    def test_shape(self, n: int, rounds: int) -> None:
        plans = generate_bracket(n)
        assert round_count(n) == rounds
        assert len(plans) == n - 1
        for r in range(1, rounds + 1):
            positions = [p.position for p in plans if p.round == r]
            assert positions == list(range(n >> r))

    def test_eight_team_first_round_pairs(self) -> None:
        first = [(p.seed_a, p.seed_b) for p in generate_bracket(8) if p.round == 1]
        assert first == [(1, 8), (4, 5), (2, 7), (3, 6)]

    def test_later_rounds_start_without_seeds(self) -> None:
        assert all(
            p.seed_a is None and p.seed_b is None for p in generate_bracket(8) if p.round > 1
        )

    def test_next_match_links(self) -> None:
        plans = {(p.round, p.position): p for p in generate_bracket(8)}
        assert plans[(1, 0)].next == NextMatchRef(2, 0, "A")
        assert plans[(1, 1)].next == NextMatchRef(2, 0, "B")
        assert plans[(1, 2)].next == NextMatchRef(2, 1, "A")
        assert plans[(1, 3)].next == NextMatchRef(2, 1, "B")
        assert plans[(2, 1)].next == NextMatchRef(3, 0, "B")
        assert plans[(3, 0)].next is None

    @pytest.mark.parametrize("n", [4, 8, 16])
    def test_every_non_final_match_feeds_an_existing_slot_exactly_once(self, n: int) -> None:
        plans = generate_bracket(n)
        keys = {(p.round, p.position) for p in plans}
        targets = [(p.next.round, p.next.position, p.next.slot) for p in plans if p.next]
        assert len(targets) == len(set(targets)) == n - 2
        assert all((r, pos) in keys for r, pos, _ in targets)

    @pytest.mark.parametrize("n", [4, 8, 16])
    def test_top_two_seeds_only_meet_in_final(self, n: int) -> None:
        order = seed_order(n)
        # Seed 1 is in the first half of the bracket, seed 2 in the second half.
        assert order.index(1) < n // 2 <= order.index(2)

    @pytest.mark.parametrize("n", [0, 2, 3, 6, 32])
    def test_unsupported_team_counts(self, n: int) -> None:
        with pytest.raises(InvalidBracketError):
            generate_bracket(n)


class TestAdvancement:
    def test_next_match_for_final_is_none(self) -> None:
        assert next_match(3, 0, 3) is None

    def test_place_winner_in_slot_a(self) -> None:
        assert place_winner(MatchTeams[str](None, None), "A", "t1") == MatchTeams("t1", None)

    def test_place_winner_in_slot_b_keeps_a(self) -> None:
        assert place_winner(MatchTeams("t1", None), "B", "t2") == MatchTeams("t1", "t2")

    def test_place_same_winner_twice_is_idempotent(self) -> None:
        assert place_winner(MatchTeams("t1", None), "A", "t1") == MatchTeams("t1", None)

    def test_overwriting_another_team_raises(self) -> None:
        with pytest.raises(InvalidStateError):
            place_winner(MatchTeams("t1", None), "A", "t9")

    def test_full_8_team_tournament_advances_top_seed(self) -> None:
        # Higher seed (lower number) always wins: final must be seed 1 vs seed 2.
        plans = generate_bracket(8)
        rounds = round_count(8)
        teams: dict[tuple[int, int], MatchTeams[int]] = {
            (p.round, p.position): MatchTeams(p.seed_a, p.seed_b) for p in plans
        }
        for p in plans:
            current = teams[(p.round, p.position)]
            assert current.team_a is not None and current.team_b is not None
            winner = min(current.team_a, current.team_b)
            ref = next_match(p.round, p.position, rounds)
            if ref is not None:
                key = (ref.round, ref.position)
                teams[key] = place_winner(teams[key], ref.slot, winner)
        assert teams[(3, 0)] == MatchTeams(1, 2)
