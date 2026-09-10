import asyncio
import threading
from unittest.mock import patch

import httpx
import pytest

from core.extractors.ocr.tesseract_provider import TesseractOcrProvider
from core.orchestrator import _file_operation
from llm.http_utils import request_with_retries


@pytest.mark.asyncio
async def test_cancel_closes_active_http_connection_without_retry():
    started = asyncio.Event()
    disconnected = asyncio.Event()
    requests = 0

    async def serve(reader, writer):
        nonlocal requests
        requests += 1
        try:
            await reader.readuntil(b"\r\n\r\n")
            started.set()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            disconnected.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server, httpx.AsyncClient() as client:
        port = server.sockets[0].getsockname()[1]
        task = asyncio.create_task(request_with_retries(
            "test", lambda: client.get(f"http://127.0.0.1:{port}/")
        ))
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(disconnected.wait(), 2)
            assert requests == 1
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_during_retry_delay():
    waiting = asyncio.Event()
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async def delay(*args):
        waiting.set()
        await asyncio.Event().wait()

    with patch("llm.http_utils.retry_delay", new=delay):
        task = asyncio.create_task(request_with_retries("test", request))
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls == 1


@pytest.mark.asyncio
async def test_file_operation_finishes_before_cancel_returns(tmp_path):
    started = threading.Event()
    release = threading.Event()
    target = tmp_path / "output"

    def write():
        started.set()
        release.wait(timeout=2)
        target.write_text("finished")

    task = asyncio.create_task(_file_operation(write))
    await asyncio.to_thread(started.wait, 2)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert target.read_text() == "finished"


def test_ocr_preparation_is_lazy_and_cached():
    with patch("core.extractors.ocr.tesseract_provider._runtime_root", return_value=None) as prepare:
        provider = TesseractOcrProvider()
        prepare.assert_not_called()
        assert provider.runtime_root is None
        assert provider.runtime_root is None
        prepare.assert_called_once()