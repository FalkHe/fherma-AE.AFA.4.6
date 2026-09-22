"""WI1 (sprint 004-02): `service.fetch_source`. `SRD_ROOT` is monkeypatched
to `tmp_path` so nothing touches the real `backend/content/srd/`; the
network is never real -- `service.build_http_client` is monkeypatched to
return an `httpx.Client` built on `httpx.MockTransport`, per
`core/llm/service.py`'s `build_sdk_client` seam."""

import httpx
import pytest

from app.modules.srd import service
from app.modules.srd.errors import SrdSourceError


@pytest.fixture(autouse=True)
def srd_root(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "SRD_ROOT", tmp_path)
    return tmp_path


def _stub_client(handler):
    def _build():
        return httpx.Client(transport=httpx.MockTransport(handler))

    return _build


def test_fetch_source_stores_the_body_at_srd_root_version_filename(monkeypatch, srd_root):
    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(200, content=b"# Title\n\nBody.\n")),
    )

    path = service.fetch_source()

    expected = srd_root / service.SOURCE_VERSION / service.SOURCE_FILENAME
    assert path == expected
    assert path.read_bytes() == b"# Title\n\nBody.\n"


def test_fetch_source_overwrites_on_a_second_call(monkeypatch, srd_root):
    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(200, content=b"first")),
    )
    first_path = service.fetch_source()
    assert first_path.read_bytes() == b"first"

    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(200, content=b"second, and longer")),
    )
    second_path = service.fetch_source()

    assert second_path == first_path
    assert second_path.read_bytes() == b"second, and longer"


def test_fetch_source_on_non_2xx_response_raises_and_leaves_existing_file_untouched(
    monkeypatch, srd_root
):
    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(200, content=b"existing")),
    )
    path = service.fetch_source()
    before = path.read_bytes()

    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(500, content=b"server error")),
    )

    with pytest.raises(SrdSourceError):
        service.fetch_source()

    assert path.read_bytes() == before


def test_fetch_source_on_transport_error_raises_and_leaves_existing_file_untouched(
    monkeypatch, srd_root
):
    monkeypatch.setattr(
        service,
        "build_http_client",
        _stub_client(lambda request: httpx.Response(200, content=b"existing")),
    )
    path = service.fetch_source()
    before = path.read_bytes()

    def _raise(request):
        raise httpx.ConnectError("no connection", request=request)

    monkeypatch.setattr(service, "build_http_client", _stub_client(_raise))

    with pytest.raises(SrdSourceError):
        service.fetch_source()

    assert path.read_bytes() == before
