"""schemas.py - Pydantic v2 data contracts shared by simulator, tools, validator and UI."""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Verdict(str, Enum):
    PASS = "PASS"
    INDETERMINATE = "INDETERMINATE"
    FAIL = "FAIL"


class FaultCode(str, Enum):
    UV_LAMP_DECAY = "UV_LAMP_DECAY"
    RESIN_EXHAUSTION = "RESIN_EXHAUSTION"
    VALVE_DIAPHRAGM_LEAK = "VALVE_DIAPHRAGM_LEAK"
    N2_PURIFIER_SATURATION = "N2_PURIFIER_SATURATION"
    SENSOR_DRIFT = "SENSOR_DRIFT"
    RO_MEMBRANE_DEGRADATION = "RO_MEMBRANE_DEGRADATION"
    AMC_FILTER_BREAKTHROUGH = "AMC_FILTER_BREAKTHROUGH"
    NO_CONFIRMED_EXCURSION = "NO_CONFIRMED_EXCURSION"


class SensorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    parameter: str
    unit: str
    asset_id: str
    direction: Literal["lower", "upper"]      # lower: value must be >= limit; upper: <= limit
    limit: float
    half_width: float = Field(ge=0)           # instrument uncertainty half-width, same unit
    limit_source: str                         # always carries the "to be verified" tag
    last_cal: str                             # ISO date
    cal_due: str                              # ISO date


class Alarm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    tag: str
    triggered_at: str
    description: str


class EvidenceItem(BaseModel):
    """One tool result, stored verbatim so every number in a report can be traced."""
    model_config = ConfigDict(extra="forbid")
    id: str                                   # E1, E2, ...
    tool: str
    args: dict
    output: dict


class HypothesisAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: FaultCode
    status: Literal["supported", "ruled_out", "unresolved"]
    evidence_ids: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    """What the LLM is allowed to produce. Verdicts and hold advisories are NOT in here:
    they are computed by code (triage) and attached afterwards."""
    model_config = ConfigDict(extra="forbid")
    root_cause_code: FaultCode
    confidence: Literal["low", "medium", "high"]
    hypotheses: list[HypothesisAssessment] = Field(min_length=1, max_length=5)
    supporting_evidence_ids: list[str] = Field(min_length=1)
    knowledge_base_citations: list[str] = Field(default_factory=list, max_length=5)   # chunk ids such as UPW-02
    narrative: str = Field(min_length=20, max_length=2500)
    recommended_actions: list[str] = Field(min_length=1, max_length=6)


class ValidationResult(BaseModel):
    ok: bool
    violations: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    """Everything the UI shows; also what a recorded trace stores."""
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    scenario_id: str
    mode: Literal["live-gemini", "replay", "scripted-offline"]
    models: dict = Field(default_factory=dict)
    alarm: dict
    notes_scan: dict
    triage: dict
    evidence: list[EvidenceItem]
    report: Optional[InvestigationReport] = None
    validation: ValidationResult
    hold_advisory: str
    status: str
    recorded_at: Optional[str] = None
    tool_rounds: int = 0
    quality_flags: list[str] = Field(default_factory=list)   # computed by code from the evidence; need acknowledgement at sign-off
    quality_notes: list[str] = Field(default_factory=list)   # informational only (e.g. a tool error the agent recovered from)
