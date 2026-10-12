import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';

import '../models.dart';
import '../widgets/match_card.dart';
import '../widgets/status_chip.dart';

/// The bracket of one tournament. Two snapshot listeners: the tournament
/// document (name, status) and its `matches` subcollection (one doc per match).
class BracketScreen extends StatelessWidget {
  const BracketScreen({
    super.key,
    required this.tournamentId,
    required this.initialName,
  });

  final String tournamentId;
  final String initialName;

  static const _wideLayoutMinWidth = 720.0;

  @override
  Widget build(BuildContext context) {
    final tournamentRef = FirebaseFirestore.instance
        .collection('tournaments')
        .doc(tournamentId);

    return StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
      stream: tournamentRef.snapshots(),
      builder: (context, tournamentSnapshot) {
        final data = tournamentSnapshot.data?.data();
        final tournament = data == null
            ? null
            : TournamentView.fromMap(tournamentId, data);

        return StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
          stream: tournamentRef.collection('matches').snapshots(),
          builder: (context, matchesSnapshot) {
            final rounds = matchesSnapshot.hasData
                ? groupByRound(
                    matchesSnapshot.data!.docs.map(
                      (doc) => MatchView.fromMap(doc.id, doc.data()),
                    ),
                  )
                : const <List<MatchView>>[];

            return LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= _wideLayoutMinWidth;
                final body = matchesSnapshot.hasError
                    ? Center(child: Text('Error: ${matchesSnapshot.error}'))
                    : rounds.isEmpty
                    ? const Center(child: CircularProgressIndicator())
                    : wide
                    ? _ColumnsBracket(rounds: rounds)
                    : _TabbedRounds(rounds: rounds);

                final appBar = AppBar(
                  title: Text(tournament?.name ?? initialName),
                  actions: [
                    if (tournament != null)
                      Padding(
                        padding: const EdgeInsets.only(right: 12),
                        child: StatusChip.tournament(tournament.status),
                      ),
                  ],
                  bottom: wide || rounds.isEmpty
                      ? null
                      : TabBar(
                          isScrollable: rounds.length > 3,
                          tabs: [
                            for (final round in rounds)
                              Tab(text: _roundTitle(round, rounds.length)),
                          ],
                        ),
                );

                final scaffold = Scaffold(appBar: appBar, body: body);
                return wide || rounds.isEmpty
                    ? scaffold
                    : DefaultTabController(
                        length: rounds.length,
                        child: scaffold,
                      );
              },
            );
          },
        );
      },
    );
  }
}

String _roundTitle(List<MatchView> round, int totalRounds) =>
    roundName(round.first.round, totalRounds);

/// Wide screens: one column per round, side by side, like a printed bracket.
class _ColumnsBracket extends StatelessWidget {
  const _ColumnsBracket({required this.rounds});

  final List<List<MatchView>> rounds;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final round in rounds)
            SizedBox(
              width: 300,
              child: Padding(
                padding: const EdgeInsets.only(right: 16),
                child: _RoundColumn(
                  title: _roundTitle(round, rounds.length),
                  matches: round,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _RoundColumn extends StatelessWidget {
  const _RoundColumn({required this.title, required this.matches});

  final String title;
  final List<MatchView> matches;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Text(title, style: Theme.of(context).textTheme.titleMedium),
        ),
        for (final match in matches)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: MatchCard(match: match),
          ),
      ],
    );
  }
}

/// Phones: one tab per round.
class _TabbedRounds extends StatelessWidget {
  const _TabbedRounds({required this.rounds});

  final List<List<MatchView>> rounds;

  @override
  Widget build(BuildContext context) {
    return TabBarView(
      children: [
        for (final round in rounds)
          ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: round.length,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder: (_, index) => MatchCard(match: round[index]),
          ),
      ],
    );
  }
}
