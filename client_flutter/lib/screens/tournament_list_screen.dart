import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';

import '../models.dart';
import '../widgets/status_chip.dart';
import 'bracket_screen.dart';

/// Lists tournaments from the read model, most recently updated first.
class TournamentListScreen extends StatelessWidget {
  const TournamentListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final query = FirebaseFirestore.instance
        .collection('tournaments')
        .orderBy('updatedAt', descending: true)
        .limit(20);

    return Scaffold(
      appBar: AppBar(title: const Text('Pickleball Live')),
      body: StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
        stream: query.snapshots(),
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return _Message('Could not load tournaments:\n${snapshot.error}');
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final tournaments = snapshot.data!.docs
              .map((doc) => TournamentView.fromMap(doc.id, doc.data()))
              .toList();
          if (tournaments.isEmpty) {
            return const _Message(
              'No tournaments yet.\nRun `make seed` in the backend to create one.',
            );
          }
          return ListView.separated(
            itemCount: tournaments.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final tournament = tournaments[index];
              return ListTile(
                leading: const Icon(Icons.emoji_events_outlined),
                title: Text(tournament.name),
                subtitle: Text('${tournament.rounds} rounds'),
                trailing: StatusChip.tournament(tournament.status),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => BracketScreen(
                      tournamentId: tournament.id,
                      initialName: tournament.name,
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Text(text, textAlign: TextAlign.center),
    ),
  );
}
