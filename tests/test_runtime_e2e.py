import time
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

from app.main import create_app
from core.config import Settings


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, provider: str) -> str | None:
        return self.values.get(provider)

    async def set(self, provider: str, value: str) -> None:
        self.values[provider] = value

    async def delete(self, provider: str) -> None:
        self.values.pop(provider, None)


def test_runtime_processes_docx_and_exposes_all_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("E-mail: email@example.test")
    document.save(source)
    secret_store = MemorySecretStore()
    app = create_app(
        settings=Settings(data_dir=tmp_path / "runtime", env="development"),
        secret_store=secret_store,
    )

    with TestClient(app) as client, source.open("rb") as stream:
        created = client.post(
            "/api/jobs",
            files={"file": (source.name, stream, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"entity_types": "email"},
        )
        assert created.status_code == 200
        job_id = created.json()["job_id"]
        status = None
        for _ in range(100):
            status = client.get(f"/api/jobs/{job_id}").json()
            if status["status"] in {"done", "failed", "needs_clarification"}:
                break
            time.sleep(0.02)

        assert status is not None and status["status"] == "done"
        assert status["total_replacements"] == 1
        report = client.get(f"/api/jobs/{job_id}/report")
        xlsx = client.get(f"/api/jobs/{job_id}/report.xlsx")
        result = client.get(f"/api/jobs/{job_id}/document")
        assert report.status_code == xlsx.status_code == result.status_code == 200
        assert report.json()["total_replacements"] == 1
        assert b"email@example.test" not in result.content


def test_provider_keys_are_isolated_and_write_only(tmp_path: Path) -> None:
    secret_store = MemorySecretStore()
    app = create_app(
        settings=Settings(data_dir=tmp_path / "runtime", env="development"),
        secret_store=secret_store,
    )
    first = "openai-secret-value"
    second = "anthropic-secret-value"

    with TestClient(app) as client:
        assert client.put(
            "/api/config",
            json={"provider": "openai", "model": "test", "api_key": first},
        ).status_code == 200
        response = client.put(
            "/api/config",
            json={"provider": "anthropic", "model": "test", "api_key": second},
        )
        fetched = client.get("/api/config")

    assert response.status_code == 200
    assert first not in response.text and second not in response.text
    assert first not in fetched.text and second not in fetched.text
    assert secret_store.values == {"openai": first, "anthropic": second}
