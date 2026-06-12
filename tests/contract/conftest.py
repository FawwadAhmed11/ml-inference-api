import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import torch
from model_serve.app import create_app
from slowapi import Limiter
from slowapi.util import get_remote_address
from testcontainers.compose import DockerCompose


@pytest.fixture
def client(monkeypatch):
    mock_model = MagicMock()
    mock_model.return_value = torch.tensor([[0.1] * 1000])
    monkeypatch.setattr("torch.load", lambda *args, **kwargs: mock_model)
    
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    monkeypatch.setattr("model_serve.app.redis_client", mock_redis)
    
    # patch the limiter storage to use memory instead of Redis
    from limits.storage import MemoryStorage
    import model_serve.app as app_module
    app_module.limiter._limiter.storage = MemoryStorage()
    
    from model_serve.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c



