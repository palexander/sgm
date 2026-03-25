from __future__ import annotations

import os

from sgm.domain.models import GraphConnectionConfig


def load_graph_connection_config() -> GraphConnectionConfig:
    return GraphConnectionConfig(
        host=os.environ.get("SGM_MEMGRAPH_HOST", "127.0.0.1"),
        port=int(os.environ.get("SGM_MEMGRAPH_PORT", "7687")),
        username=os.environ.get("SGM_MEMGRAPH_USERNAME", ""),
        password=os.environ.get("SGM_MEMGRAPH_PASSWORD", ""),
        encrypted=os.environ.get("SGM_MEMGRAPH_ENCRYPTED", "false").lower() == "true",
        lazy=os.environ.get("SGM_MEMGRAPH_LAZY", "false").lower() == "true",
    )

