import 'package:flutter/material.dart';

import '../models.dart';
import 'status_chip.dart';

/// One match: both teams, the score of each game, and a status label.
///
/// When a newer version of the match arrives with a different score, the card
/// flashes briefly and the changed numbers animate in.
class MatchCard extends StatefulWidget {
  const MatchCard({super.key, required this.match});

  final MatchView match;

  @override
  State<MatchCard> createState() => _MatchCardState();
}

class _MatchCardState extends State<MatchCard>
    with SingleTickerProviderStateMixin {
  static const highlightDuration = Duration(milliseconds: 900);

  late final AnimationController _highlight = AnimationController(
    vsync: this,
    duration: highlightDuration,
    value: 1, // start "settled": no flash on first build
  );

  @override
  void didUpdateWidget(MatchCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.match;
    final current = widget.match;
    final scoreChanged =
        previous.id == current.id &&
        current.version > previous.version &&
        (!_sameGames(previous.games, current.games) ||
            previous.status != current.status);
    if (scoreChanged) _highlight.forward(from: 0);
  }

  @override
  void dispose() {
    _highlight.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final match = widget.match;
    final scheme = Theme.of(context).colorScheme;
    final base = scheme.surfaceContainerLow;
    final flash = scheme.tertiaryContainer;

    return AnimatedBuilder(
      animation: _highlight,
      builder: (context, child) => Card(
        margin: EdgeInsets.zero,
        color: Color.lerp(
          flash,
          base,
          Curves.easeOut.transform(_highlight.value),
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(
            color: match.isLive ? scheme.error : scheme.outlineVariant,
            width: match.isLive ? 1.5 : 1,
          ),
        ),
        child: child,
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text(
                  'Match ${match.position + 1}',
                  style: Theme.of(context).textTheme.labelMedium,
                ),
                const Spacer(),
                StatusChip.match(match.status),
              ],
            ),
            const SizedBox(height: 8),
            _TeamRow(match: match, team: match.teamA, side: _Side.a),
            const SizedBox(height: 6),
            _TeamRow(match: match, team: match.teamB, side: _Side.b),
          ],
        ),
      ),
    );
  }
}

bool _sameGames(List<GameScore> x, List<GameScore> y) {
  if (x.length != y.length) return false;
  for (var i = 0; i < x.length; i++) {
    if (x[i] != y[i]) return false;
  }
  return true;
}

enum _Side { a, b }

class _TeamRow extends StatelessWidget {
  const _TeamRow({required this.match, required this.team, required this.side});

  final MatchView match;
  final TeamView? team;
  final _Side side;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final isWinner = match.isWinner(team);
    final lost = match.isFinished && !isWinner;

    return Row(
      children: [
        SizedBox(
          width: 22,
          child: Text(
            team == null ? '' : '${team!.seed}',
            style: textTheme.labelSmall?.copyWith(color: scheme.outline),
          ),
        ),
        Expanded(
          child: Text(
            team?.name ?? 'TBD',
            overflow: TextOverflow.ellipsis,
            style: textTheme.bodyLarge?.copyWith(
              fontWeight: isWinner ? FontWeight.w700 : FontWeight.w400,
              color: team == null || lost ? scheme.outline : null,
            ),
          ),
        ),
        for (var i = 0; i < match.games.length; i++)
          _GameScoreBox(
            value: side == _Side.a ? match.games[i].a : match.games[i].b,
            current: match.isLive && i == match.games.length - 1,
          ),
      ],
    );
  }
}

class _GameScoreBox extends StatelessWidget {
  const _GameScoreBox({required this.value, required this.current});

  final int value;
  final bool current;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final style = Theme.of(context).textTheme.titleMedium?.copyWith(
      fontFeatures: const [FontFeature.tabularFigures()],
      fontWeight: current ? FontWeight.w700 : FontWeight.w400,
      color: current ? scheme.primary : null,
    );
    return SizedBox(
      width: 32,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        transitionBuilder: (child, animation) =>
            ScaleTransition(scale: animation, child: child),
        child: Text(
          '$value',
          key: ValueKey(value),
          textAlign: TextAlign.right,
          style: style,
        ),
      ),
    );
  }
}
