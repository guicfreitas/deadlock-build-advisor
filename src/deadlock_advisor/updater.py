"""Self-update from GitHub Releases.

The installed .exe checks https://api.github.com/repos/<repo>/releases/latest at startup and
every few hours. A newer release's installer (DeadlockBuildAdvisor-Setup-<ver>.exe) is
downloaded in the background, checked against its SHA-256 (GitHub's asset "digest", or a
"<asset>.sha256" file in the release) and run with Inno Setup's /SILENT flags: it installs
over the current copy, and the installer's [Run] entry for silent installs reopens the app.

It never installs during a match: the app would close while the player needs the build.
Running from source only reports that a new version exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_REPO = "guicfreitas/deadlock-build-advisor"
ASSET_RE = re.compile(r"^DeadlockBuildAdvisor-Setup-[\w.\-]+\.exe$", re.I)
CHECK_EVERY_S = 6 * 3600
FIRST_CHECK_S = 15          # let the app finish starting first
BUSY_RETRY_S = 60
USER_AGENT = "deadlock-build-advisor-updater"


def parse_version(v: str) -> tuple[int, ...]:
    """'v0.2.10' -> (0, 2, 10). Anything after the numbers (-beta...) is ignored."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(remote: str, current: str) -> bool:
    r, c = parse_version(remote), parse_version(current)
    n = max(len(r), len(c))
    return bool(r) and r + (0,) * (n - len(r)) > c + (0,) * (n - len(c))


@dataclass
class Release:
    version: str
    url: str                 # installer download URL
    name: str                # installer file name
    size: int
    sha256: str | None       # hex
    notes: str = ""
    page: str = ""


def _get(url: str, accept: str = "application/vnd.github+json", timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_release(data: dict) -> Release | None:
    """Pick the installer out of a GitHub release JSON (None: drafts or no installer)."""
    if data.get("draft") or data.get("prerelease"):
        return None
    assets = data.get("assets") or []
    exe = next((a for a in assets if ASSET_RE.match(a.get("name", ""))), None)
    if not exe:
        return None
    digest = exe.get("digest") or ""
    sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None
    if not sha:
        side = next((a for a in assets if a.get("name") == exe["name"] + ".sha256"), None)
        if side:
            try:
                sha = _get(side["browser_download_url"], "application/octet-stream").decode().split()[0].lower()
            except Exception:  # noqa: BLE001 - treated as "no checksum" below
                sha = None
    return Release(data.get("tag_name", ""), exe["browser_download_url"], exe["name"],
                   int(exe.get("size") or 0), sha, data.get("body") or "", data.get("html_url") or "")


def latest_release(repo: str) -> Release | None:
    return parse_release(json.loads(_get(f"https://api.github.com/repos/{repo}/releases/latest")))


def download(rel: Release, dest_dir: Path, progress: Callable[[int, int], None] | None = None) -> Path:
    """Download and verify the installer. Refuses a release without a SHA-256."""
    if not rel.sha256 or not re.fullmatch(r"[0-9a-f]{64}", rel.sha256):
        raise RuntimeError("a versão nova não tem checksum SHA-256; não vou instalar")
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / rel.name
    if final.exists() and _sha256(final) == rel.sha256:
        return final
    part = final.with_suffix(".part")
    h, done = hashlib.sha256(), 0
    req = urllib.request.Request(rel.url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or rel.size or 0)
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if h.hexdigest() != rel.sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError("o download não bate com o checksum; descartado")
    part.replace(final)
    for old in dest_dir.glob("DeadlockBuildAdvisor-Setup-*.exe"):  # keep only the newest
        if old != final:
            old.unlink(missing_ok=True)
    return final


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# AppId from packaging/installer.iss; Inno registers the install under "<AppId>_is1"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C1E0B9A-5D7E-4C2B-9C1F-3E1D2B6A8F41}_is1"


def _same_dir(a: str, b: str) -> bool:
    norm = lambda p: os.path.normcase(os.path.normpath(p.strip().strip('"')))
    return bool(a and b) and norm(a) == norm(b)


def registered_scope(app_dir: str) -> str | None:
    """'user' or 'machine': which uninstall entry (HKCU or HKLM) points at this folder."""
    try:
        import winreg
    except ImportError:
        return None
    for hive, scope in ((winreg.HKEY_CURRENT_USER, "user"), (winreg.HKEY_LOCAL_MACHINE, "machine")):
        try:
            with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                if _same_dir(winreg.QueryValueEx(k, "InstallLocation")[0], app_dir):
                    return scope
        except OSError:
            continue
    return None


def installer_args(exe_path: str, scope: str | None = None) -> list[str]:
    """Silent Inno Setup flags that update the copy that is running, in place: same scope
    and same folder. Getting the scope wrong installs a second copy: on 2026-11-12 a per-user
    install in G:\\ was guessed as all-users (not under LOCALAPPDATA) and 0.2.1 landed in
    Program Files next to it. The registry is the truth; the path is only a fallback."""
    app_dir = os.path.dirname(exe_path)
    args = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    scope = scope or registered_scope(app_dir)
    if scope is None:
        local = os.environ.get("LOCALAPPDATA", "")
        scope = "user" if local and os.path.normcase(exe_path).startswith(os.path.normcase(local)) else "machine"
    args.append("/CURRENTUSER" if scope == "user" else "/ALLUSERS")
    if app_dir:
        args.append(f"/DIR={app_dir}")
    return args


class Updater:
    """Background check/download/install; publishes its state as state["update"]."""

    def __init__(self, state, current: str, repo: str, *, frozen: bool, download_dir: Path,
                 auto: Callable[[], bool], busy: Callable[[], bool], quit_app: Callable[[], None]):
        self.state, self.current, self.repo = state, current, repo
        self.frozen, self.download_dir = frozen, download_dir
        self.auto, self.busy, self.quit_app = auto, busy, quit_app
        self.release: Release | None = None
        self.installer: Path | None = None
        self._lock = threading.Lock()
        self._installing = False
        self._view = {"state": "idle", "current": current, "available": False, "version": None,
                      "message": "", "can_install": frozen}

    def _publish(self, **kw) -> None:
        self._view.update(kw)
        self.state.update(update=dict(self._view))

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="updater").start()

    def _loop(self) -> None:
        time.sleep(FIRST_CHECK_S)
        next_check = 0.0
        while True:
            if time.time() >= next_check and not self.installer:
                next_check = time.time() + CHECK_EVERY_S
                try:
                    self.check_and_prepare()
                except Exception as e:  # noqa: BLE001 - offline, GitHub down, rate limit...
                    traceback.print_exc()
                    # quiet: an unreachable GitHub is not worth a banner unless we had news
                    self._publish(state="error" if self._view["available"] else "idle",
                                  message=f"Não consegui baixar a atualização: {e}")
            if self.ready_to_auto_install():
                self.install()
                return
            time.sleep(BUSY_RETRY_S)

    def ready_to_auto_install(self) -> bool:
        """Auto-install only out of a match: the app closes while it installs."""
        return bool(self.installer) and self.frozen and self.auto() and not self.busy()

    def check_and_prepare(self) -> None:
        rel = latest_release(self.repo)
        if not rel or not is_newer(rel.version, self.current):
            self._publish(state="uptodate", available=False, message="")
            return
        self.release = rel
        ver = rel.version.lstrip("v")
        if not self.frozen:
            self._publish(state="available", available=True, version=ver,
                          message=f"Versão {ver} disponível (você roda do código-fonte: atualize com git pull).")
            return
        self._publish(state="downloading", available=True, version=ver,
                      message=f"Baixando a versão {ver}…")
        last = [0.0]

        def progress(done, total):
            if total and time.time() - last[0] > 1:
                last[0] = time.time()
                self._publish(message=f"Baixando a versão {ver}… {100 * done // total}%")
        self.installer = download(rel, self.download_dir, progress)
        self._publish(state="ready", message=(
            f"Versão {ver} baixada. Instala sozinha quando você não estiver em partida."
            if self.auto() else f"Versão {ver} pronta para instalar."))

    def install(self) -> dict:
        """Run the downloaded installer and close the app (the installer reopens it)."""
        with self._lock:
            if not self.frozen:
                return {"error": "rodando do código-fonte: atualize com git pull"}
            if not self.installer or not self.installer.exists():
                return {"error": "nenhuma atualização baixada ainda"}
            if self._installing:
                return {"ok": True}
            self._installing = True
        self._publish(state="installing", message="Instalando a atualização… o app reabre sozinho.")
        try:
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([str(self.installer), *installer_args(sys.executable)],
                             creationflags=flags, close_fds=True)
        except OSError as e:
            self._installing = False
            self._publish(state="error", message=f"Não consegui abrir o instalador: {e}")
            return {"error": str(e)}
        # leave before the installer replaces our files (it also closes us via /CLOSEAPPLICATIONS)
        threading.Timer(1.0, self.quit_app).start()
        return {"ok": True}
