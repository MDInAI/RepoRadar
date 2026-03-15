from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal[
    "overlord",
    "firehose",
    "backfill",
    "bouncer",
    "analyst",
    "combiner",
    "obsession",
]


AgentConfigInputKind = Literal["integer", "date", "csv"]


class AgentConfigFieldResponse(BaseModel):
    key: str
    label: str
    description: str
    input_kind: AgentConfigInputKind
    value: str
    unit: str | None = None
    min_value: int | None = None
    placeholder: str | None = None


class AgentConfigResponse(BaseModel):
    agent_name: AgentName
    display_name: str
    editable: bool
    summary: str
    apply_notes: list[str] = Field(default_factory=list)
    fields: list[AgentConfigFieldResponse] = Field(default_factory=list)


class AgentConfigUpdateRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class AgentConfigUpdateResponse(AgentConfigResponse):
    message: str
