from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MarketDataReference:
    dataset_id: str
    source_id: str
    asset: str
    instrument: str
    data_type: str
    timeframe: str
    storage_backend: str

    def parquet_path(self, root: Path, year: int, month: int) -> Path:
        if self.storage_backend != "parquet":
            raise ValueError("parquet_path is only valid for parquet-backed datasets")
        return (
            root
            / f"source={self.source_id}"
            / f"type={self.data_type}"
            / f"asset={self.asset}"
            / f"timeframe={self.timeframe}"
            / f"year={year:04d}"
            / f"month={month:02d}"
            / "data.parquet"
        )
