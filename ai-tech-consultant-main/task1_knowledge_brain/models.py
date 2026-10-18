
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    history: list[ChatMessage] = Field(default_factory=list)


class Source(BaseModel):
    title: str
    url: str
    source_id: str | None = None
    snippet: str | None = None
    score: float | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    needs_human_help: bool = False


class SyncRequest(BaseModel):
    max_pages: int | None = Field(default=20, ge=1)
    delay_seconds: float = Field(default=1.0, ge=0)
