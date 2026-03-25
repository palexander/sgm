from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SystemAdapter:
    def new_proposal_id(self) -> str:
        return f"prop-{uuid4().hex[:6]}"

    def now(self) -> datetime:
        return datetime.now()

