import 'package:flutter/material.dart';

/// Small colored label for match / tournament status.
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, required this.live});

  factory StatusChip.match(String status) => StatusChip(
    label: switch (status) {
      'live' => 'LIVE',
      'finished' => 'FINAL',
      _ => 'UPCOMING',
    },
    live: status == 'live',
  );

  factory StatusChip.tournament(String status) => StatusChip(
    label: switch (status) {
      'in_progress' => 'LIVE',
      'finished' => 'FINISHED',
      _ => 'SCHEDULED',
    },
    live: status == 'in_progress',
  );

  final String label;
  final bool live;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final background = live ? scheme.error : scheme.surfaceContainerHighest;
    final foreground = live ? scheme.onError : scheme.onSurfaceVariant;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: foreground,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.6,
          ),
        ),
      ),
    );
  }
}
