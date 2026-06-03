from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def _parse_days(value: str) -> int:
    if not value.endswith("d"):
        raise ValueError(f"Only day durations are supported for v1, got {value!r}")
    days = int(value[:-1])
    if days <= 0:
        raise ValueError(f"Duration must be positive, got {value!r}")
    return days


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    template_id: str
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    oos_start: date
    oos_end: date


@dataclass(frozen=True, slots=True)
class WalkForwardTemplate:
    template_id: str
    retrain_cadence: str
    train_range: str
    validation_range: str
    oos_range: str
    embargo: str
    anchor: str = "rolling"

    def materialize(self, as_of: date) -> WalkForwardWindow:
        if self.anchor != "rolling":
            raise ValueError(f"Unsupported v1 walk-forward anchor: {self.anchor!r}")

        train_days = _parse_days(self.train_range)
        validation_days = _parse_days(self.validation_range)
        oos_days = _parse_days(self.oos_range)
        embargo_days = _parse_days(self.embargo) if self.embargo != "0d" else 0

        oos_start = as_of
        oos_end = oos_start + timedelta(days=oos_days - 1)
        validation_end = oos_start - timedelta(days=embargo_days + 1)
        validation_start = validation_end - timedelta(days=validation_days - 1)
        train_end = validation_start - timedelta(days=embargo_days + 1)
        train_start = train_end - timedelta(days=train_days - 1)

        return WalkForwardWindow(
            template_id=self.template_id,
            train_start=train_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            oos_start=oos_start,
            oos_end=oos_end,
        )
