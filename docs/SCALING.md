# Scaling notes

The write path (scorekeepers → Cloud Run → Postgres) carries a few requests per second, even for
a large event: a rally takes 10–30 s in real play. The interesting dimension is the **read
fan-out**, the number of spectators receiving every change.

## How Firestore bills this design

- Every document a listener receives counts as **one read**: the initial snapshot of each
  document, then one read per changed document per listener.
- Each publish costs **one write plus one read**: the version check inside the transaction.
- A listener that reconnects after more than 30 minutes offline is billed for a full re-read.

So read cost grows with **updates × viewers**. Write cost does not depend on viewers at all.

## Cost formula

For one tournament with `N` teams, where every viewer listens to the whole bracket:

```
matches                 M = N - 1
updates per match       U ≈ points per match + 3   (start, finish, the winner placed in the next match)
reads per viewer        R_v = (1 + M)              initial snapshot: tournament doc + match docs
                            + M × U                every match update
                            + T                    tournament doc updates (3: in_progress, finished, …)
total reads             R = V × R_v                V = concurrent viewers
read cost               C_r = R / 100,000 × P_read
write cost              C_w = M × U × (P_write + P_read) / 100,000   (negligible; independent of V)
```

Assumptions for the example below:
- A best-of-3 to 11 with rally scoring is about 40–60 points, so take `U ≈ 50`.
- `P_read`/`P_write` are prices per 100k operations. **Firestore prices vary by location (regional
  vs multi-region) and change over time. Check the current pricing page.** The ranges below use
  roughly $0.03–$0.06 per 100k reads.

| Scenario | N | V | R_v ≈ 8 + 7×50 + 3 | Total reads R | Read cost per tournament |
|---|---|---|---|---|---|
| Club event | 8 | 500 | 361 | ~180k | ~$0.05–$0.11 |
| Spec target | 8 | 2,000 | 361 | ~720k | ~$0.22–$0.43 |
| Big stream | 8 | 200,000 | 361 | ~72M | ~$22–$43 |
| Big stream, 16 teams | 16 | 200,000 | 16 + 15×50 + 3 ≈ 769 | ~154M | ~$46–$92 |

The free daily quota (on the order of 50k reads per day) only covers development and small tests.
At 200k concurrent viewers the cost is still modest per tournament, but it is linear. Several tournaments per day, or a viewer base
that reconnects often, multiply it.

## Hundreds to ~2k spectators

Use this design as is. The read cost is negligible, Cloud Run is idle between scorekeeper
requests, and Postgres sees a handful of writes per second.

## ~200k spectators

What changes, in order of impact:

1. **Listen to less.** Today a viewer listens to every match document. Instead:
   - Add a small `tournaments/{id}/summary` document holding one line per match (status, games
     won, winner). The relay updates it only on **structural** changes (start, game won,
     finish, advance), about 5 per match instead of ~50.
   - Clients listen to the summary to draw the bracket. They open a listener on a per-match
     document only for the one or two live matches the user is actually looking at.
   - Reads per viewer drop from `M × U` to roughly `5 × M + U × (matches watched)`. For 8 teams
     that is about 35 + 100 instead of 350, a reduction of 2–3×. It grows to an order of
     magnitude for larger brackets.
2. **Batch updates in 1–2 s windows.** Replace the per-write fast path with a relay that drains
   on a short timer. The existing coalescing already publishes only the newest version per match,
   so a 2 s window collapses bursts (fast play, corrections) into one write. In real play a point
   takes 10+ s, so this matters most for bursts and corrections.
3. **Keep documents small.** Payload size drives bandwidth, not read count, but the per-match
   documents are already about 300 bytes. Keep history (per-point logs) out of the read model.
4. **Mind the connection limits.** Firestore supports up to about 1M concurrent client
   connections per database; check the current quotas. One listener per active screen keeps
   each client to one connection.
5. **Re-evaluate the transport.** At this scale, compare against:
   - a dedicated pub/sub service (Ably, Pusher, a self-hosted Centrifugo), priced per message
     or per connection;
   - a CDN-cached JSON snapshot, refreshed every 1–2 s and polled by clients, where cost
     scales with CDN requests and the origin sees ~1 request/s regardless of the audience.
   The outbox relay is the single integration point, so adding a second publisher does not touch
   the write path.

## Not covered here (next steps)

- **Load tests**: k6 or Locust for the write path, plus a listener swarm against a staging
  Firestore to validate fan-out latency and cost.
- **Multi-region**: a regional Postgres primary with a Firestore multi-region database, and
  Cloud Run in several regions behind a global load balancer.
- **CDN caching** of `GET /bracket` as a fallback for clients without Firestore.
