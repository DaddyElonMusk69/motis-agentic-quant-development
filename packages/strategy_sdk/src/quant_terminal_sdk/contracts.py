from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class SignalEnvelope:
    signal_id: str
    signal_engine_id: str
    signal_engine_version: str
    asset: str
    instrument: str
    timestamp: str
    data_refs: list[str]
    payload_schema: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyContext:
    signal: SignalEnvelope
    runtime_mode: Literal["backtest", "paper", "live"]
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)
    derived_features: dict[str, Any] = field(default_factory=dict)
    portfolio_state: dict[str, Any] = field(default_factory=dict)
    prior_strategy_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    decision_id: str
    strategy_id: str
    strategy_version: str
    signal_id: str
    action: Literal["ENTER", "SKIP", "EXIT", "HOLD"]
    direction: Literal["LONG", "SHORT", "FLAT"]
    confidence: float
    reason_code: str
    execution_profile: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
