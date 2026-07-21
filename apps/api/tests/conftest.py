from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from tests.fakes import FakeProvider
from tests.optional_gates import (
    CLOUD_PRICING_PATH,
    install_verified_cloud_pricing,
    restore_cloud_pricing,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def verified_cloud_pricing() -> Generator[Path, None, None]:
    """Ensure config/cloud_pricing.json is verified for budget/eligibility tests."""
    path, previous = install_verified_cloud_pricing(CLOUD_PRICING_PATH)
    try:
        yield path
    finally:
        restore_cloud_pricing(path, previous)


@pytest.fixture
def testing_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unit.db'}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(tmp_path, fake_provider: FakeProvider) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: testing_session
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake_provider])
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
