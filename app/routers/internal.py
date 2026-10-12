"""Internal endpoints, called by Cloud Scheduler (not by clients)."""

from fastapi import APIRouter, Depends, Request

from app.auth import require_internal_token
from app.outbox.relay import OutboxRelay
from app.schemas import DrainResultOut

router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_token)]
)


def get_relay(request: Request) -> OutboxRelay:
    relay: OutboxRelay = request.app.state.relay
    return relay


@router.post(
    "/outbox/drain",
    summary="Publish pending outbox events",
    description=(
        "Safety net for the post-commit fast path. Cloud Scheduler calls it every minute with "
        "the `X-Internal-Token` header."
    ),
)
async def drain_outbox(relay: OutboxRelay = Depends(get_relay)) -> DrainResultOut:
    result = await relay.drain_until_empty()
    return DrainResultOut(
        published=result.published, failed=result.failed, remaining=result.remaining
    )
