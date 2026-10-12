"""Push notifications for key match events, sent to the FCM topic `tournament_{id}`.

FCM is behind the FCM_ENABLED flag; in dev the LoggingNotifier just logs what would be sent.
"""

import asyncio
from typing import Any, Protocol

import structlog

from app.config import Settings

logger = structlog.get_logger()


class Notifier(Protocol):
    async def notify(self, topic: str, title: str, body: str, data: dict[str, str]) -> None: ...


class LoggingNotifier:
    async def notify(self, topic: str, title: str, body: str, data: dict[str, str]) -> None:
        logger.info("notification", topic=topic, title=title, body=body, data=data)


class FcmNotifier:
    """Uses the Firebase Admin SDK with Application Default Credentials (no key files)."""

    def __init__(self, project_id: str) -> None:
        import firebase_admin

        try:
            self._app = firebase_admin.get_app()
        except ValueError:
            self._app = firebase_admin.initialize_app(options={"projectId": project_id})

    async def notify(self, topic: str, title: str, body: str, data: dict[str, str]) -> None:
        from firebase_admin import messaging

        message = messaging.Message(
            topic=topic,
            notification=messaging.Notification(title=title, body=body),
            data=data,
        )
        # The Admin SDK is synchronous; keep it off the event loop.
        await asyncio.to_thread(messaging.send, message, app=self._app)


def create_notifier(settings: Settings) -> Notifier:
    return FcmNotifier(settings.gcp_project_id) if settings.fcm_enabled else LoggingNotifier()


def match_notification(
    event_type: str, match_id: str, payload: dict[str, Any]
) -> tuple[str, str, str, dict[str, str]] | None:
    """(topic, title, body, data) for match_started / match_finished, else None."""
    if event_type not in ("match_started", "match_finished"):
        return None
    team_a = (payload.get("teamA") or {}).get("name", "TBD")
    team_b = (payload.get("teamB") or {}).get("name", "TBD")
    topic = f"tournament_{payload['tournamentId']}"
    data = {"matchId": match_id, "event": event_type}
    if event_type == "match_started":
        return topic, "Match started", f"{team_a} vs {team_b}", data

    games = payload.get("games", [])
    score = ", ".join(f"{g['a']}-{g['b']}" for g in games)
    winner_id = payload.get("winnerTeamId")
    winner = team_a if winner_id == (payload.get("teamA") or {}).get("id") else team_b
    return topic, "Final result", f"{winner} wins: {team_a} vs {team_b} ({score})", data
