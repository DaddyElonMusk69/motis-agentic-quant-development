from __future__ import annotations

from typing import Any


STRATEGY_ID = "bollinger_base"
STRATEGY_VERSION = "v0.1"


def decide(context: dict[str, Any]) -> dict[str, Any]:
    signal = context.get("signal") or {}
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    interactions = evidence.get("interactions") if isinstance(evidence.get("interactions"), list) else []
    if not interactions:
        return _decision(
            signal_id=str(signal.get("signal_id", "unknown")),
            action="SKIP",
            direction="FLAT",
            confidence=0.2,
            reason_code="missing_bollinger_interactions",
            diagnostics={"interaction_count": 0},
        )

    upper_votes = sum(1 for interaction in interactions if interaction.get("band") == "upper")
    lower_votes = sum(1 for interaction in interactions if interaction.get("band") == "lower")
    if upper_votes == lower_votes:
        return _decision(
            signal_id=signal["signal_id"],
            action="SKIP",
            direction="FLAT",
            confidence=0.35,
            reason_code="balanced_upper_lower_band_votes",
            diagnostics=_diagnostics(evidence, upper_votes=upper_votes, lower_votes=lower_votes),
        )
    if upper_votes > lower_votes:
        return _decision(
            signal_id=signal["signal_id"],
            action="ENTER",
            direction="SHORT",
            confidence=_confidence(upper_votes, lower_votes),
            reason_code="upper_band_reversion_setup",
            diagnostics=_diagnostics(evidence, upper_votes=upper_votes, lower_votes=lower_votes),
        )
    return _decision(
        signal_id=signal["signal_id"],
        action="ENTER",
        direction="LONG",
        confidence=_confidence(lower_votes, upper_votes),
        reason_code="lower_band_reversion_setup",
        diagnostics=_diagnostics(evidence, upper_votes=upper_votes, lower_votes=lower_votes),
    )


def manage_position(context: dict[str, Any]) -> dict[str, Any]:
    position_context = context.get("position_context") if isinstance(context.get("position_context"), dict) else {}
    if position_context.get("hard_exit_expired") is True:
        return {"action": "EXIT", "reason_code": "hard_exit_expired"}
    return {"action": "HOLD", "reason_code": "mechanical_policy"}


def _confidence(primary_votes: int, opposing_votes: int) -> float:
    total = primary_votes + opposing_votes
    if total <= 0:
        return 0.2
    return round(min(0.85, 0.5 + (primary_votes - opposing_votes) / max(total, 1) * 0.25), 2)


def _diagnostics(evidence: dict[str, Any], *, upper_votes: int, lower_votes: int) -> dict[str, Any]:
    return {
        "pattern": evidence.get("pattern"),
        "bb_period": evidence.get("bb_period"),
        "bb_stddev": evidence.get("bb_stddev"),
        "vote_threshold": evidence.get("vote_threshold"),
        "active_timeframes": evidence.get("active_timeframes", []),
        "upper_votes": upper_votes,
        "lower_votes": lower_votes,
    }


def _decision(
    *,
    signal_id: str,
    action: str,
    direction: str,
    confidence: float,
    reason_code: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_id": f"{STRATEGY_ID}-{STRATEGY_VERSION}-{signal_id}",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "signal_id": signal_id,
        "action": action,
        "trade_action": action,
        "direction": direction,
        "confidence": confidence,
        "reason_code": reason_code,
        "diagnostics": diagnostics,
    }
