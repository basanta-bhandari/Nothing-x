import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .variants import build_info, variant_id

REPOSITORY = "basanta-bhandari/Nothing-x"
API = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"


def version_number(value):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", str(value)):
        raise ValueError("The release version is invalid.")
    return tuple(int(part) for part in str(value).removeprefix("v").split("."))


def release_url(value):
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc == "github.com" and parsed.path.startswith("/" + REPOSITORY + "/releases/download/") and not parsed.query and not parsed.fragment


def select_artifact(manifest, variant, system=None, arch=None):
    system = system or ("macos" if sys.platform == "darwin" else "linux")
    arch = arch or platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(arch, arch)
    for item in manifest.get("artifacts", []):
        if item.get("variant") == variant and item.get("os") in (system, "any") and item.get("arch") in (arch, "any"):
            if not re.fullmatch(r"[A-Za-z0-9._-]+", item.get("file", "")) or not re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", "")):
                raise ValueError("The release checksum or filename is invalid.")
            if not isinstance(item.get("size"), int) or not 0 < item["size"] <= 1024 ** 3:
                raise ValueError("The release file size is invalid.")
            return item
    raise ValueError("This release has no package for " + variant + " on this system.")


class Updater(QObject):
    status = Signal(str)
    available = Signal(bool)
    ready_to_restart = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.busy = False
        self.release = None
        self.artifact = None
        self.manifest = None
        self.reply = None
        self.directory = None

    def fetch_json(self, url, callback):
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"NothingX/0.4.0")
        request.setTransferTimeout(20000)
        reply = self.network.get(request)
        self.reply = reply
        reply.downloadProgress.connect(lambda received, total: reply.abort() if received > 1024 ** 2 else None)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError("Could not check releases: " + reply.errorString())
                data = bytes(reply.readAll())
                if len(data) > 1024 ** 2:
                    raise ValueError("The release metadata is too large.")
                value = json.loads(data)
                if not isinstance(value, dict):
                    raise ValueError("The release metadata is invalid.")
                callback(value)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.fail(str(error))
            finally:
                if self.reply is reply:
                    self.reply = None
                reply.deleteLater()
        reply.finished.connect(finished)

    def check(self):
        if self.busy:
            return
        self.busy = True
        self.artifact = None
        self.available.emit(False)
        self.status.emit("Checking " + variant_id() + "…")
        self.fetch_json(API, self.received_release)

    def received_release(self, release):
        if release.get("draft") or release.get("prerelease"):
            raise ValueError("No stable release is available.")
        version = version_number(release.get("tag_name"))
        if version <= version_number(__version__):
            self.busy = False
            self.status.emit("You’re up to date · " + __version__)
            return
        self.release = release
        asset = next((item for item in release.get("assets", []) if item.get("name") == "nothingx-update.json"), {})
        url = asset.get("browser_download_url", "")
        if not release_url(url):
            raise ValueError("This release does not include an update manifest.")
        self.fetch_json(url, self.received_manifest)

    def received_manifest(self, manifest):
        if version_number(manifest.get("version")) != version_number(self.release["tag_name"]):
            raise ValueError("The release and manifest versions do not match.")
        if not re.fullmatch(r"[a-f0-9]{40}", manifest.get("commit", "")):
            raise ValueError("The release commit is missing.")
        artifact = select_artifact(manifest, variant_id())
        asset = next((item for item in self.release.get("assets", []) if item.get("name") == artifact["file"]), None)
        if not asset or not release_url(asset.get("browser_download_url", "")) or asset.get("size") != artifact["size"]:
            raise ValueError("The release package is missing or has changed.")
        self.manifest = manifest
        self.artifact = {**artifact, "url": asset["browser_download_url"]}
        self.busy = False
        if build_info().get("managed"):
            self.status.emit("Version " + manifest["version"] + " available. Update through your package manager.")
            return
        self.status.emit("Version " + manifest["version"] + " available · " + variant_id())
        self.available.emit(True)

    def install(self):
        if self.busy or not self.artifact:
            return
        self.busy = True
        self.available.emit(False)
        self.directory = Path(tempfile.mkdtemp(prefix="nothingx-update-"))
        path = self.directory / self.artifact["file"]
        output = path.open("wb")
        digest = hashlib.sha256()
        received = [0]
        request = QNetworkRequest(QUrl(self.artifact["url"]))
        request.setTransferTimeout(60000)
        reply = self.network.get(request)
        self.reply = reply

        def drain():
            data = bytes(reply.readAll())
            received[0] += len(data)
            if received[0] > self.artifact["size"]:
                reply.abort()
                return
            output.write(data)
            digest.update(data)
            self.status.emit(f"Downloading · {received[0] * 100 // self.artifact['size']}%")

        def finished():
            try:
                drain()
                output.close()
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError("Download failed: " + reply.errorString())
                if received[0] != self.artifact["size"] or digest.hexdigest() != self.artifact["sha256"]:
                    raise ValueError("The download checksum did not match. Nothing was installed.")
                self.prepare_install(path)
            except (ValueError, OSError, RuntimeError) as error:
                self.fail(str(error))
            finally:
                output.close()
                if self.reply is reply:
                    self.reply = None
                reply.deleteLater()
        reply.readyRead.connect(drain)
        reply.finished.connect(finished)

    def prepare_install(self, artifact):
        info = build_info()
        variant = variant_id()
        backend, distribution = variant.split("-", 1)
        root = Path(__file__).resolve().parents[1]
        source = Path(info.get("source", root)).resolve()
        appimage = os.environ.get("APPIMAGE")
        bundle = next((parent for parent in Path(sys.executable).parents if parent.suffix == ".app"), None) if sys.platform == "darwin" else None
        if distribution == "portable" and sys.platform != "darwin" and not appimage:
            raise ValueError("Open the AppImage file to update this portable installation.")
        if distribution == "manual" and not (source / ".git").exists():
            raise ValueError("The source checkout is missing. Clone the repository again to use source updates.")
        restart = [appimage, "--connect"] if appimage else [str(bundle / "Contents/MacOS/nothingx"), "--connect"] if bundle else [sys.executable, "-m", "nothingx", "--backend", backend, "--connect"]
        plan = {"backend": backend, "distribution": distribution, "version": self.manifest["version"], "commit": self.manifest["commit"], "artifact": str(artifact), "sha256": self.artifact["sha256"], "parent": os.getpid(), "root": str(root), "source": str(source), "appimage": appimage, "bundle": str(bundle) if bundle else None, "restart": restart}
        plan_path = self.directory / "plan.json"
        plan_path.write_text(json.dumps(plan))
        log = Path.home() / ("Library/Logs/NothingX" if sys.platform == "darwin" else ".cache/nothingx") / "update.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            command = [appimage or sys.executable, "--apply-update", str(plan_path)]
        else:
            helper = self.directory / "apply.py"
            shutil.copy2(Path(__file__).with_name("update_install.py"), helper)
            command = [sys.executable, str(helper), str(plan_path)]
        with log.open("w") as output:
            subprocess.Popen(command, cwd=root, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        self.status.emit("Installing update. The app will restart.")
        self.ready_to_restart.emit()

    def fail(self, message):
        self.busy = False
        self.status.emit(message)
        self.available.emit(bool(self.artifact))

    def close(self):
        if self.reply and self.reply.isRunning():
            self.reply.abort()
