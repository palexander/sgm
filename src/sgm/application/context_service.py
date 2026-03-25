from __future__ import annotations

from dataclasses import dataclass, replace

from sgm.adapters.repository import GraphRepository
from sgm.domain.models import GoverningSpec, RelatedDecision, SpecContextResponse, SpecDelta
from sgm.domain.spec_deltas import build_spec_delta


@dataclass(slots=True)
class ContextService:
    graph_repository: GraphRepository

    def context(self, spec_ref: str) -> SpecContextResponse:
        response: SpecContextResponse = self.graph_repository.get_context(spec_ref)
        spec: GoverningSpec = self._with_spec_deltas((response.spec,))[0]
        return SpecContextResponse(
            spec=spec,
            decisions=self._active_decisions(response.decisions),
            governed_files=response.governed_files,
            pending_proposals=response.pending_proposals,
        )

    def _with_spec_deltas(
        self,
        specs: tuple[GoverningSpec, ...],
    ) -> tuple[GoverningSpec, ...]:
        enriched_specs: list[GoverningSpec] = []
        for spec in specs:
            spec_delta: SpecDelta | None = build_spec_delta(
                spec_id=spec.id,
                source_path=spec.source_path,
                previous_text=spec.previous_source_text,
                current_text=spec.source_text,
            )
            enriched_specs.append(replace(spec, spec_delta=spec_delta))
        return tuple(enriched_specs)

    def _active_decisions(
        self,
        decisions: tuple[RelatedDecision, ...],
    ) -> tuple[RelatedDecision, ...]:
        return decisions
