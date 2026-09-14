import os
from pathlib import Path

import pytest
from app.core.config import load_environment_file


def test_load_environment_file_exports_provider_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DASHSCOPE_API_KEY=test-key\n", encoding="utf-8")

    load_environment_file(env_file)

    assert os.environ["DASHSCOPE_API_KEY"] == "test-key"
