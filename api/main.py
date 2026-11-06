"""HTTP API for the web UI. Meant for local use: bind it to the loopback address."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException
from pydantic import Field, StringConstraints

from satellitecreator.equipment import UnknownEquipmentError
from satellitecreator.intake import UnknownQuestionError
from satellitecreator.schema import Frozen
from satellitecreator.session import SessionResult, run_session

MAX_PROMPT_LENGTH = 4000
MAX_ANSWER_LENGTH = 2000
MAX_ANSWERS = 32
MAX_EQUIPMENT = 16

PromptText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_PROMPT_LENGTH)
]
AnswerText = Annotated[str, StringConstraints(max_length=MAX_ANSWER_LENGTH)]


class SessionRequest(Frozen):
    prompt: PromptText
    answers: dict[str, AnswerText] = Field(default_factory=dict, max_length=MAX_ANSWERS)
    equipment: tuple[str, ...] = Field(default=(), max_length=MAX_EQUIPMENT)


class HealthResponse(Frozen):
    status: str


def create_app() -> FastAPI:
    application = FastAPI(title="SatelliteCreator API")

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/session", response_model=SessionResult)
    def session(request: SessionRequest) -> SessionResult:
        try:
            return run_session(request.prompt, request.answers, request.equipment)
        except (UnknownQuestionError, UnknownEquipmentError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return application


app = create_app()
