/// Read-only views of the Firestore read model documents written by the backend
/// (see `app/readmodel/projector.py`). Parsing is pure so it can be unit tested.
library;

int _int(Object? value) => (value as num?)?.toInt() ?? 0;

class TeamView {
  const TeamView({required this.id, required this.name, required this.seed});

  final String id;
  final String name;
  final int seed;

  static TeamView? fromMap(Object? data) {
    if (data is! Map) return null;
    return TeamView(
      id: data['id'] as String? ?? '',
      name: data['name'] as String? ?? 'TBD',
      seed: _int(data['seed']),
    );
  }
}

class GameScore {
  const GameScore(this.a, this.b);

  final int a;
  final int b;

  @override
  bool operator ==(Object other) =>
      other is GameScore && other.a == a && other.b == b;

  @override
  int get hashCode => Object.hash(a, b);
}

class MatchView {
  const MatchView({
    required this.id,
    required this.round,
    required this.position,
    required this.teamA,
    required this.teamB,
    required this.status,
    required this.games,
    required this.winnerTeamId,
    required this.version,
  });

  final String id;
  final int round;
  final int position;
  final TeamView? teamA;
  final TeamView? teamB;
  final String status; // pending | live | finished
  final List<GameScore> games;
  final String? winnerTeamId;
  final int version;

  factory MatchView.fromMap(String id, Map<String, dynamic> data) {
    final games = (data['games'] as List<dynamic>? ?? const [])
        .whereType<Map<dynamic, dynamic>>()
        .map((g) => GameScore(_int(g['a']), _int(g['b'])))
        .toList();
    return MatchView(
      id: id,
      round: _int(data['round']),
      position: _int(data['position']),
      teamA: TeamView.fromMap(data['teamA']),
      teamB: TeamView.fromMap(data['teamB']),
      status: data['status'] as String? ?? 'pending',
      games: games,
      winnerTeamId: data['winnerTeamId'] as String?,
      version: _int(data['version']),
    );
  }

  bool get isLive => status == 'live';
  bool get isFinished => status == 'finished';

  bool isWinner(TeamView? team) =>
      team != null && winnerTeamId != null && team.id == winnerTeamId;
}

class TournamentView {
  const TournamentView({
    required this.id,
    required this.name,
    required this.status,
    required this.rounds,
    required this.version,
  });

  final String id;
  final String name;
  final String status; // scheduled | in_progress | finished
  final int rounds;
  final int version;

  factory TournamentView.fromMap(String id, Map<String, dynamic> data) =>
      TournamentView(
        id: id,
        name: data['name'] as String? ?? 'Tournament',
        status: data['status'] as String? ?? 'scheduled',
        rounds: _int(data['rounds']),
        version: _int(data['version']),
      );
}

/// "Final", "Semifinals", "Quarterfinals", else "Round N".
String roundName(int round, int totalRounds) {
  final fromEnd = totalRounds - round;
  return switch (fromEnd) {
    0 => 'Final',
    1 => 'Semifinals',
    2 => 'Quarterfinals',
    _ => 'Round $round',
  };
}

/// Matches grouped by round (index 0 = round 1), each round sorted by position.
List<List<MatchView>> groupByRound(Iterable<MatchView> matches) {
  final byRound = <int, List<MatchView>>{};
  for (final match in matches) {
    byRound.putIfAbsent(match.round, () => []).add(match);
  }
  final rounds = byRound.keys.toList()..sort();
  return [
    for (final round in rounds)
      byRound[round]!..sort((x, y) => x.position.compareTo(y.position)),
  ];
}
