import hashlib

import pytest

from deadlock_advisor import updater as u


def test_versions():
    assert u.parse_version("v0.2.10") == (0, 2, 10)
    assert u.is_newer("v0.2.0", "0.1.9") and u.is_newer("0.10", "0.9.5")
    assert not u.is_newer("v0.2", "0.2.0") and not u.is_newer("garbage", "0.1.0")


def release(**exe):
    return {"tag_name": "v0.3.0", "html_url": "page", "body": "notas", "assets": [
        {"name": "notes.txt", "browser_download_url": "x"},
        {"name": "DeadlockBuildAdvisor-Setup-0.3.0.exe", "browser_download_url": "dl", "size": 10} | exe]}


def test_parse_release_reads_github_digest():
    r = u.parse_release(release(digest="sha256:" + "AB" * 32))
    assert r.version == "v0.3.0" and r.url == "dl" and r.sha256 == "ab" * 32
    assert u.parse_release(release() | {"draft": True}) is None
    assert u.parse_release({"tag_name": "v1", "assets": []}) is None


def test_parse_release_falls_back_to_sidecar(monkeypatch):
    data = release()
    data["assets"].append({"name": "DeadlockBuildAdvisor-Setup-0.3.0.exe.sha256", "browser_download_url": "side"})
    monkeypatch.setattr(u, "_get", lambda url, *a, **k: ("cd" * 32 + "  file.exe").encode())
    assert u.parse_release(data).sha256 == "cd" * 32


class FakeResp:
    def __init__(self, data):
        self.data, self.headers = data, {"Content-Length": str(len(data))}

    def read(self, n=-1):
        out, self.data = self.data[:n], self.data[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_verifies_checksum(tmp_path, monkeypatch):
    payload = b"installer bytes" * 1000
    monkeypatch.setattr(u.urllib.request, "urlopen", lambda *a, **k: FakeResp(payload))
    rel = u.Release("v0.3.0", "https://x/dl", "DeadlockBuildAdvisor-Setup-0.3.0.exe", len(payload),
                    hashlib.sha256(payload).hexdigest())
    path = u.download(rel, tmp_path)
    assert path.read_bytes() == payload
    bad = u.Release("v0.3.1", "https://x/dl", "DeadlockBuildAdvisor-Setup-0.3.1.exe", 0, "0" * 64)
    with pytest.raises(RuntimeError):
        u.download(bad, tmp_path)
    assert not list(tmp_path.glob("*0.3.1*"))           # nothing half-downloaded is kept
    with pytest.raises(RuntimeError):
        u.download(u.Release("v1", "https://x/dl", "x.exe", 0, None), tmp_path)   # no checksum, no install


def test_installer_args_keep_the_install_scope(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\me\AppData\Local")
    assert "/CURRENTUSER" in u.installer_args(r"C:\Users\me\AppData\Local\Programs\DBA\app.exe")
    assert "/ALLUSERS" in u.installer_args(r"C:\Program Files\DBA\app.exe")
    assert "/SILENT" in u.installer_args("x")


class State:
    def __init__(self):
        self.data = {}

    def update(self, **kw):
        self.data.update(kw)


def make(tmp_path, monkeypatch, frozen=True, auto=True, busy=False):
    rel = u.Release("v9.0.0", "dl", "DeadlockBuildAdvisor-Setup-9.0.0.exe", 1, "a" * 64)
    monkeypatch.setattr(u, "latest_release", lambda repo: rel)
    monkeypatch.setattr(u, "download", lambda rel, d, progress=None: tmp_path / rel.name)
    return u.Updater(State(), "0.2.0", "o/r", frozen=frozen, download_dir=tmp_path,
                     auto=lambda: auto, busy=lambda: busy, quit_app=lambda: None)


def test_waits_for_the_match_to_end(tmp_path, monkeypatch):
    up = make(tmp_path, monkeypatch, busy=True)
    up.check_and_prepare()
    assert up.state.data["update"]["state"] == "ready" and not up.ready_to_auto_install()
    up.busy = lambda: False
    assert up.ready_to_auto_install()
    up.auto = lambda: False
    assert not up.ready_to_auto_install()


def test_source_checkout_only_notifies(tmp_path, monkeypatch):
    up = make(tmp_path, monkeypatch, frozen=False)
    up.check_and_prepare()
    view = up.state.data["update"]
    assert view["state"] == "available" and view["version"] == "9.0.0" and not view["can_install"]
    assert up.installer is None and "error" in up.install()


def test_up_to_date(tmp_path, monkeypatch):
    up = make(tmp_path, monkeypatch)
    up.current = "9.0.0"
    up.check_and_prepare()
    assert up.state.data["update"]["state"] == "uptodate" and not up.installer
