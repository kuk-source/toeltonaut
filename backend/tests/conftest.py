import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

# Must be set BEFORE any app module is imported
_tmp = tempfile.mkdtemp()
os.environ["UPLOADS_DIR"] = os.path.join(_tmp, "uploads")
os.environ["OUTPUTS_DIR"] = os.path.join(_tmp, "outputs")
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/toeltonaut"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only!!"

# Stub heavy / unavailable native libs
for _mod in ("cv2", "ultralytics", "imageio_ffmpeg"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Stub app.database so SQLAlchemy never tries to load psycopg.
# get_db must be a proper async generator so FastAPI dependency injection works.
_mock_session = AsyncMock()
_mock_result = MagicMock()
_mock_result.scalars.return_value.all.return_value = []
_mock_result.scalar_one_or_none.return_value = None
_mock_session.execute = AsyncMock(return_value=_mock_result)


async def _mock_get_db():
    yield _mock_session


_db_stub = MagicMock()
_db_stub.get_db = _mock_get_db
_db_stub.init_db = AsyncMock()
_db_stub.engine = MagicMock()
_db_stub.AsyncSessionLocal = MagicMock()
sys.modules["app.database"] = _db_stub

import pytest
from unittest.mock import patch


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from fastapi.testclient import TestClient
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main._migrate_add_training_columns"),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
