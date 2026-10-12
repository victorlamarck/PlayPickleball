"""Pydantic request/response models (the public API contract)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.scoring import Team

TEAM_NAMES_EXAMPLE = [
    "Dink Dynasty",
    "Kitchen Kings",
    "Third Shot Drop",
    "Erne Express",
    "Lob City",
    "Net Ninjas",
    "Paddle Pirates",
    "Spin Doctors",
]


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Dink Dynasty"])


class CreateTournamentRequest(BaseModel):
    """Teams are seeded in list order: the first team is seed 1."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Demo Open", "teams": [{"name": n} for n in TEAM_NAMES_EXAMPLE]}]
        }
    )

    name: str = Field(min_length=1, max_length=200, description="Tournament name.")
    teams: list[TeamIn] = Field(description="4, 8 or 16 teams, ordered by seed (first = seed 1).")


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str = Field(examples=["Dink Dynasty"])
    seed: int = Field(examples=[1])


class TournamentOut(BaseModel):
    id: uuid.UUID
    name: str = Field(examples=["Demo Open"])
    status: Literal["scheduled", "in_progress", "finished"]
    rounds: int = Field(examples=[3], description="Number of rounds (log2 of the team count).")
    version: int = Field(examples=[1])
    teams: list[TeamOut]
    created_at: datetime
    updated_at: datetime


class GameOut(BaseModel):
    a: int = Field(examples=[11])
    b: int = Field(examples=[7])


class MatchOut(BaseModel):
    id: uuid.UUID
    tournament_id: uuid.UUID
    round: int = Field(examples=[1], description="1 = first round.")
    position: int = Field(examples=[0], description="0-based index within the round.")
    team_a: TeamOut | None = Field(description="Empty until the feeding match finishes.")
    team_b: TeamOut | None
    status: Literal["pending", "live", "finished"]
    games: list[GameOut] = Field(examples=[[{"a": 11, "b": 7}, {"a": 4, "b": 2}]])
    winner_team_id: uuid.UUID | None
    next_match_id: uuid.UUID | None = Field(description="Null for the final.")
    next_slot: Literal["A", "B"] | None
    version: int = Field(
        examples=[23], description="Incremented on every change. Send it back as expected_version."
    )
    updated_at: datetime


class RoundOut(BaseModel):
    round: int = Field(examples=[1])
    matches: list[MatchOut]


class BracketOut(BaseModel):
    tournament: TournamentOut
    rounds: list[RoundOut]


class PointRequest(BaseModel):
    team: Team = Field(description="Team that won the rally.", examples=["A"])
    expected_version: int = Field(ge=1, description="Match version the client last saw.")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"team": "A", "expected_version": 3}]}
    )


class GameCorrectionRequest(BaseModel):
    a: int = Field(ge=0, examples=[11])
    b: int = Field(ge=0, examples=[9])
    expected_version: int = Field(ge=1, examples=[12])


class DrainResultOut(BaseModel):
    published: int = Field(examples=[42], description="Events marked as published.")
    failed: int = Field(examples=[0], description="Events whose publish attempt failed.")
    remaining: int = Field(examples=[0], description="Events still pending.")


class ErrorDetail(BaseModel):
    code: str = Field(examples=["version_conflict"])
    message: str = Field(examples=["The resource was modified by another request"])
    details: dict[str, Any] = Field(examples=[{"current_version": 7, "expected_version": 6}])


class ErrorResponse(BaseModel):
    error: ErrorDetail
