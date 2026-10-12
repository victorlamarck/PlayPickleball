import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pickleball_live_viewer/models.dart';
import 'package:pickleball_live_viewer/widgets/match_card.dart';

MatchView liveMatch({required int version, required List<GameScore> games}) =>
    MatchView(
      id: 'm1',
      round: 1,
      position: 0,
      teamA: const TeamView(id: 'a', name: 'Dink Dynasty', seed: 1),
      teamB: const TeamView(id: 'b', name: 'Spin Doctors', seed: 8),
      status: 'live',
      games: games,
      winnerTeamId: null,
      version: version,
    );

Widget wrap(MatchView match) => MaterialApp(
  theme: ThemeData(useMaterial3: true),
  home: Scaffold(body: MatchCard(match: match)),
);

Color cardColor(WidgetTester tester) =>
    tester.widget<Card>(find.byType(Card)).color!;

void main() {
  testWidgets('shows teams, seeds, game scores and LIVE', (tester) async {
    await tester.pumpWidget(
      wrap(
        liveMatch(version: 5, games: const [GameScore(11, 7), GameScore(4, 2)]),
      ),
    );

    expect(find.text('Dink Dynasty'), findsOneWidget);
    expect(find.text('Spin Doctors'), findsOneWidget);
    expect(find.text('8'), findsOneWidget);
    expect(find.text('11'), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('LIVE'), findsOneWidget);
  });

  testWidgets('shows TBD and UPCOMING for a future match', (tester) async {
    await tester.pumpWidget(
      wrap(
        const MatchView(
          id: 'm2',
          round: 2,
          position: 0,
          teamA: null,
          teamB: null,
          status: 'pending',
          games: [],
          winnerTeamId: null,
          version: 1,
        ),
      ),
    );

    expect(find.text('TBD'), findsNWidgets(2));
    expect(find.text('UPCOMING'), findsOneWidget);
  });

  testWidgets('flashes when a newer version changes the score', (tester) async {
    await tester.pumpWidget(
      wrap(liveMatch(version: 5, games: const [GameScore(3, 2)])),
    );
    final settled = cardColor(tester);

    await tester.pumpWidget(
      wrap(liveMatch(version: 6, games: const [GameScore(4, 2)])),
    );
    await tester.pump(const Duration(milliseconds: 50));
    expect(cardColor(tester), isNot(settled));
    expect(find.text('4'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(cardColor(tester), settled);
  });

  testWidgets('does not flash for a stale or identical update', (tester) async {
    await tester.pumpWidget(
      wrap(liveMatch(version: 6, games: const [GameScore(4, 2)])),
    );
    final settled = cardColor(tester);

    await tester.pumpWidget(
      wrap(liveMatch(version: 6, games: const [GameScore(4, 2)])),
    );
    await tester.pump(const Duration(milliseconds: 50));
    expect(cardColor(tester), settled);
  });
}
