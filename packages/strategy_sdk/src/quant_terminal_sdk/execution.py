from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_notional_usd: float
    max_daily_loss_usd: float

    def __post_init__(self) -> None:
        if self.max_notional_usd <= 0:
            raise ValueError("max_notional_usd must be positive")
        if self.max_daily_loss_usd <= 0:
            raise ValueError("max_daily_loss_usd must be positive")


@dataclass(frozen=True, slots=True)
class DeploymentRoute:
    route_id: str
    strategy_id: str
    strategy_version: str
    signal_engine_id: str
    signal_engine_version: str
    asset: str
    instrument: str
    account_mode: str
    execution_adapter: str
    risk_limits: RiskLimits
    promoted: bool
    data_warmed: bool
    manually_armed: bool
    enabled: bool

    def blockers(self) -> list[str]:
        blockers: list[str] = []
        if not self.enabled:
            blockers.append("route_disabled")
        if self.account_mode == "live":
            if not self.promoted:
                blockers.append("route_not_promoted")
            if not self.data_warmed:
                blockers.append("data_not_warmed")
            if not self.manually_armed:
                blockers.append("route_not_manually_armed")
        return blockers

    def can_execute_live(self) -> bool:
        return self.account_mode == "live" and not self.blockers()
