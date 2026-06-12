# tests/integration/conftest.py
import pytest
from testcontainers.compose import DockerCompose


@pytest.fixture(scope="session")
def stack():
    with DockerCompose("./", compose_file_name="docker-compose.yaml") as c:
        c.wait_for("http://localhost:8000/health")
        yield c

