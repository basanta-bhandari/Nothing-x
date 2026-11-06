import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "basanta-bhandari/Nothing-x"
sys.path.insert(0, str(ROOT))
from nothingx import __version__


def run(*args, **options):
    return subprocess.run(list(map(str, args)), check=True, cwd=ROOT, **options)


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", "repos/" + REPOSITORY + "/" + path], text=True))


def validate_run(number, platform):
    info = api(f"actions/runs/{number}")
    if info.get("conclusion") != "success" or info.get("status") != "completed":
        raise ValueError(f"Build {number} did not complete successfully.")
    if info.get("path") != ".github/workflows/packages.yml":
        raise ValueError("The packages must come from the project package workflow.")
    jobs = api(f"actions/runs/{number}/jobs?per_page=100")["jobs"]
    selected = [job for job in jobs if job["name"].startswith("macos (")] if platform == "macos" else [job for job in jobs if job["name"] == "flatpak"]
    if len(selected) != (2 if platform == "macos" else 1) or any(job["conclusion"] != "success" for job in selected):
        raise ValueError("A required platform build is missing or failed.")
    if platform == "macos" and any(not any(step["name"] == "Check native macOS desktop widget" and step["conclusion"] == "success" for step in job["steps"]) for job in selected):
        raise ValueError("Both Mac packages must pass the native desktop widget check.")
    commit = info["head_sha"]
    run("git", "fetch", "--no-tags", "--depth=1", "origin", commit)
    run("git", "diff", "--exit-code", commit, "HEAD", "--", "nothingx", "rust-engine", "cosmic-applet", "packaging", "requirements.txt", "requirements-build.txt", "pyproject.toml", "setup.py", "setup.sh", "install-cosmic.py", "tools/install_support.py", "tools/migrate_legacy.py")


def validate_mac_archive(path):
    with zipfile.ZipFile(path) as archive:
        plists = [name for name in archive.namelist() if name.endswith(".app/Contents/Info.plist") and not name.startswith("__MACOSX/")]
        if len(plists) != 1:
            raise ValueError("A Mac archive must contain exactly one app.")
        info = plistlib.loads(archive.read(plists[0]))
        if info.get("CFBundleShortVersionString") != __version__:
            raise ValueError("The Mac app version does not match this release.")
        if info.get("CFBundleIdentifier") != "io.github.basanta_bhandari.NothingX":
            raise ValueError("Unexpected Mac app identity.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macos-run", required=True, type=int)
    parser.add_argument("--flatpak-run", required=True, type=int)
    args = parser.parse_args()
    validate_run(args.macos_run, "macos")
    validate_run(args.flatpak_run, "flatpak")
    stage = ROOT / "build/publish-artifacts"
    output = ROOT / "dist/release"
    output.mkdir(parents=True, exist_ok=True)
    run("gh", "run", "download", args.macos_run, "--repo", REPOSITORY, "--pattern", "NothingX-macos-*", "--dir", stage / "macos")
    run("gh", "run", "download", args.flatpak_run, "--repo", REPOSITORY, "--name", "NothingX-flatpak", "--dir", stage / "flatpak")
    packages = list(stage.rglob("*.dmg")) + list(stage.rglob("*.app.zip")) + list(stage.rglob("*.flatpak"))
    expected = {f"NothingX-macos-{arch}.{extension}" for arch in ("arm64", "x86_64") for extension in ("dmg", "app.zip")} | {"NothingX-linux-x86_64.flatpak"}
    if len(packages) != len(expected) or {path.name for path in packages} != expected:
        raise ValueError("The package set is incomplete or contains duplicates.")
    for path in packages:
        if path.name.endswith(".app.zip"):
            validate_mac_archive(path)
        shutil.copy2(path, output / path.name)
    run(sys.executable, "tools/build_backends.py")
    run(sys.executable, "tools/release.py", "--output", output)
    expected |= {f"NothingX-source-v{__version__}.tar.gz", "NothingX-rust-applet-linux-x86_64.tar.gz", "nothingx-update.json", "SHA256SUMS"}
    files = sorted(path for path in output.iterdir() if path.is_file())
    if {path.name for path in files} != expected:
        raise ValueError("Unexpected release files. Use a clean release output directory.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=ROOT).strip()
    tag = "v" + __version__
    existing = subprocess.run(["gh", "release", "view", tag, "--repo", REPOSITORY, "--json", "isDraft,targetCommitish"], text=True, capture_output=True)
    if existing.returncode == 0:
        draft = json.loads(existing.stdout)
        if not draft["isDraft"] or draft["targetCommitish"] != commit:
            raise ValueError("This release already exists at another commit or is already published.")
    else:
        run("gh", "release", "create", tag, "--repo", REPOSITORY, "--target", commit, "--title", "Nothing X " + __version__, "--notes-file", ROOT / f".github/release-notes/{__version__}.md", "--draft")
    run("gh", "release", "upload", tag, "--repo", REPOSITORY, "--clobber", *files)
    uploaded = json.loads(subprocess.check_output(["gh", "release", "view", tag, "--repo", REPOSITORY, "--json", "assets"], text=True))
    assets = {asset["name"]: asset for asset in uploaded["assets"]}
    if set(assets) != expected:
        raise ValueError("The uploaded release asset set does not match the verified packages.")
    for path in files:
        asset = assets[path.name]
        if asset["size"] != path.stat().st_size:
            raise ValueError("An uploaded release file has the wrong size.")
        with path.open("rb") as file:
            digest = "sha256:" + hashlib.file_digest(file, "sha256").hexdigest()
        if asset.get("digest") and asset["digest"] != digest:
            raise ValueError("An uploaded release file has the wrong checksum.")
    run("gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--latest=true")
    print(api("releases/latest")["html_url"], flush=True)


if __name__ == "__main__":
    main()
