from __future__ import annotations

from collections.abc import Generator

import pytest
from testcontainers.core.container import DockerContainer

from sgm.adapters.memgraph import MemgraphRepository
from sgm.domain.models import GraphConnectionConfig
from tests.integration.helpers import docker_available, wait_for_port


@pytest.fixture(scope="session")
def memgraph_container() -> Generator[tuple[str, int], None, None]:
    if not docker_available():
        raise pytest.skip.Exception("docker is required for integration tests")

    with DockerContainer("memgraph/memgraph:latest").with_exposed_ports(7687) as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(7687))
        wait_for_port(host=host, port=port)
        yield host, port


@pytest.fixture(autouse=True)
def reset_memgraph(memgraph_container: tuple[str, int]) -> Generator[None, None, None]:
    host, port = memgraph_container
    repository = MemgraphRepository(
        config=GraphConnectionConfig(
            host=host,
            port=port,
            username="",
            password="",
            encrypted=False,
            lazy=False,
        )
    )
    repository.reset()
    yield
    repository.reset()
