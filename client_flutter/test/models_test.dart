import 'package:flutter_test/flutter_test.dart';
import 'package:pickleball_live_viewer/models.dart';

Map<String, dynamic> matchDoc({
  int round = 1,
  int position = 0,
  String status = 'live',
  List<Map<String, int>> games = const [
    {'a': 11, 'b': 7},
    {'a': 4, 'b': 2},
  ],
  String? winner,
  int version = 23,
}) => {
  'tournamentId': 't1',
  'round': round,
  'position': position,
  'teamA': {'id': 'a', 'name': 'Dink Dynasty', 'seed': 1},
  'teamB': {'id': 'b', 'name': 'Spin Doctors', 'seed': 8},
  'status': status,
  'games': games,
  'winnerTeamId': winner,
  'version': version,
};

void main() {
  group('MatchView.fromMap', () {
    test('parses the backend projector document', () {
      final match = MatchView.fromMap('m1', matchDoc());

      expect(match.id, 'm1');
      expect(match.teamA!.name, 'Dink Dynasty');
      expect(match.teamB!.seed, 8);
      expect(match.games, const [GameScore(11, 7), GameScore(4, 2)]);
      expect(match.isLive, isTrue);
      expect(match.version, 23);
    });

    test('future match without teams or games', () {
      final match = MatchView.fromMap('m2', {
        'round': 2,
        'position': 1,
        'teamA': null,
        'teamB': null,
        'status': 'pending',
        'games': <dynamic>[],
        'winnerTeamId': null,
        'version': 1,
      });

      expect(match.teamA, isNull);
      expect(match.games, isEmpty);
      expect(match.isLive, isFalse);
    });

    test('winner detection', () {
      final match = MatchView.fromMap(
        'm1',
        matchDoc(status: 'finished', winner: 'b'),
      );

      expect(match.isFinished, isTrue);
      expect(match.isWinner(match.teamB), isTrue);
      expect(match.isWinner(match.teamA), isFalse);
    });

    test('accepts numbers decoded as doubles', () {
      final match = MatchView.fromMap('m1', {
        ...matchDoc(),
        'version': 5.0,
        'round': 2.0,
      });
      expect(match.version, 5);
      expect(match.round, 2);
    });
  });

  test('TournamentView.fromMap', () {
    final tournament = TournamentView.fromMap('t1', {
      'name': 'Demo Open',
      'status': 'in_progress',
      'rounds': 3,
      'version': 2,
    });
    expect(tournament.name, 'Demo Open');
    expect(tournament.rounds, 3);
  });

  test('roundName', () {
    expect(
      [for (var r = 1; r <= 4; r++) roundName(r, 4)],
      ['Round 1', 'Quarterfinals', 'Semifinals', 'Final'],
    );
    expect(roundName(1, 2), 'Semifinals');
  });

  test('groupByRound sorts rounds and positions', () {
    final matches = [
      MatchView.fromMap('final', matchDoc(round: 2, position: 0)),
      MatchView.fromMap('r1p1', matchDoc(round: 1, position: 1)),
      MatchView.fromMap('r1p0', matchDoc(round: 1, position: 0)),
    ];
    final rounds = groupByRound(matches);
    expect(rounds.map((r) => r.map((m) => m.id).toList()).toList(), [
      ['r1p0', 'r1p1'],
      ['final'],
    ]);
  });
}
