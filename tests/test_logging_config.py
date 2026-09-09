import logging
from pathlib import Path

from app.logging_config import configure_file_logging


def test_rotating_log_is_created_in_app_data_without_sensitive_payload(tmp_path: Path) -> None:
    target = configure_file_logging(tmp_path)
    logging.getLogger("dockmask.test").info("job_completed job_id=test")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert target == tmp_path / "dockmask.log"
    content = target.read_text(encoding="utf-8")
    assert "job_completed" in content
    assert "document text" not in content
