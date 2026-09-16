"""WI1: `service.fetch_source()` (AC1, AC3, AC5 in part).

The network boundary is `service.httpx` (a module attribute, never a name
import, per AGENTS.md's monkeypatching rule) -- every test here replaces it
with a small stand-in exposing only `.get(url, **kwargs)`, so nothing in
this file ever opens a socket. `service.SRD_ROOT` is repointed at `tmp_path`
with `monkeypatch.setattr`, following `tests/content/conftest.py`'s
`CONTENT_ROOT` precedent."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.srd import service
from app.modules.srd.errors import SrdSourceError


class _FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"some srd text"):
        self.status_code = status_code
        self.content = content


@pytest.fixture
def srd_root(tmp_path, monkeypatch):
    """Repoints `service.SRD_ROOT` at an empty `tmp_path`, requested by every
    test that calls `fetch_source` here, so nothing touches the committed
    content tree. Not requested by the one test that checks the constant's
    own, unpatched value."""
    monkeypatch.setattr(service, "SRD_ROOT", tmp_path)
    return tmp_path


def _stub_get(*, response=None, exc=None):
    calls: list[str] = []

    def get(url, **kwargs):
        calls.append(url)
        if exc is not None:
            raise exc
        return response

    return SimpleNamespace(get=get), calls


def test_stores_the_download_at_the_expected_path_creating_parent_dirs(monkeypatch, srd_root):
    fake_httpx, _ = _stub_get(response=_FakeResponse(content=b"the srd body"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    result = service.fetch_source()

    expected = srd_root / service.SOURCE_VERSION / service.SOURCE_FILENAME
    assert result == expected
    assert expected.read_bytes() == b"the srd body"


def test_a_second_run_overwrites_the_stored_file_in_place(monkeypatch, srd_root):
    fake_httpx_1, _ = _stub_get(response=_FakeResponse(content=b"first body"))
    monkeypatch.setattr(service, "httpx", fake_httpx_1)
    first_path = service.fetch_source()
    assert first_path.read_bytes() == b"first body"

    fake_httpx_2, _ = _stub_get(response=_FakeResponse(content=b"second, replacing body"))
    monkeypatch.setattr(service, "httpx", fake_httpx_2)
    second_path = service.fetch_source()

    assert second_path == first_path
    assert second_path.read_bytes() == b"second, replacing body"


def test_a_non_200_response_raises_srd_source_error(monkeypatch, srd_root):
    fake_httpx, _ = _stub_get(response=_FakeResponse(status_code=404, content=b"not found"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()


def test_a_non_200_response_leaves_an_existing_stored_file_untouched(monkeypatch, srd_root):
    dest_dir = srd_root / service.SOURCE_VERSION
    dest_dir.mkdir(parents=True)
    dest_path = dest_dir / service.SOURCE_FILENAME
    dest_path.write_bytes(b"previously stored body")

    fake_httpx, _ = _stub_get(response=_FakeResponse(status_code=500, content=b"error"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()

    assert dest_path.read_bytes() == b"previously stored body"


def test_a_timeout_raises_srd_source_error(monkeypatch, srd_root):
    fake_httpx, _ = _stub_get(exc=TimeoutError("timed out"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()


def test_a_timeout_leaves_an_existing_stored_file_untouched(monkeypatch, srd_root):
    dest_dir = srd_root / service.SOURCE_VERSION
    dest_dir.mkdir(parents=True)
    dest_path = dest_dir / service.SOURCE_FILENAME
    dest_path.write_bytes(b"previously stored body")

    fake_httpx, _ = _stub_get(exc=TimeoutError("timed out"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()

    assert dest_path.read_bytes() == b"previously stored body"


def test_an_empty_body_raises_srd_source_error(monkeypatch, srd_root):
    fake_httpx, _ = _stub_get(response=_FakeResponse(content=b""))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()


def test_an_empty_body_leaves_an_existing_stored_file_untouched(monkeypatch, srd_root):
    dest_dir = srd_root / service.SOURCE_VERSION
    dest_dir.mkdir(parents=True)
    dest_path = dest_dir / service.SOURCE_FILENAME
    dest_path.write_bytes(b"previously stored body")

    fake_httpx, _ = _stub_get(response=_FakeResponse(content=b""))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    with pytest.raises(SrdSourceError):
        service.fetch_source()

    assert dest_path.read_bytes() == b"previously stored body"


def test_fetch_source_never_touches_the_real_module_level_httpx(monkeypatch, srd_root):
    """Guards the monkeypatch seam itself: if `fetch_source` ever imported
    `httpx.get` by name instead of going through the module reference, this
    stub would be bypassed silently and the other tests here would be
    exercising nothing (AGENTS.md's module-attribute rule)."""
    fake_httpx, calls = _stub_get(response=_FakeResponse(content=b"body"))
    monkeypatch.setattr(service, "httpx", fake_httpx)

    service.fetch_source()

    assert calls == [service.SOURCE_URL]


def test_srd_root_resolves_to_content_srd_under_the_backend_package_root():
    """Sanity check on the constant itself, independent of the `srd_root`
    monkeypatch: `SRD_ROOT` must be `<backend>/content/srd`, three levels
    above `app/modules/srd/service.py` (WI1 brief). Checked structurally,
    not by a hard-coded directory name, since the backend root is named
    differently on the host (`backend/`) than inside its own container
    (`/app`)."""
    from app.modules.srd import service as unpatched_service_module

    module_path = Path(unpatched_service_module.__file__).resolve()
    assert module_path.parents[0].name == "srd"
    assert module_path.parents[1].name == "modules"
    assert module_path.parents[2].name == "app"
    backend_root = module_path.parents[3]
    assert backend_root / "content" / "srd" == unpatched_service_module.SRD_ROOT
