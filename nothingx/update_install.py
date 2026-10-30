import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time


def run(command, **options):
    print("Running:", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **options)


def safe_extract(archive, destination):
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 20000 or sum(item.size for item in members) > 1024 ** 3:
            raise ValueError("The update archive is too large.")
        for item in members:
            path = Path(item.name)
            if path.is_absolute() or ".." in path.parts or item.issym() or item.islnk() or not (item.isfile() or item.isdir()):
                raise ValueError("The update archive contains an unsafe path.")
        source.extractall(destination, members=members, filter="data")


def replace_file(source, target):
    stage = target.with_name(target.name + ".update")
    previous = target.with_name(target.name + ".previous")
    shutil.copy2(source, stage)
    stage.chmod(0o755)
    if target.exists():
        shutil.copy2(target, previous)
    os.replace(stage, target)


def replace_app(source, target):
    stage = target.with_name("." + target.name + ".update")
    previous = target.with_name(target.name + ".previous")
    shutil.rmtree(stage, ignore_errors=True)
    run(["ditto", source, stage])
    run(["codesign", "--verify", "--deep", "--strict", stage])
    shutil.rmtree(previous, ignore_errors=True)
    if target.exists():
        target.rename(previous)
    try:
        stage.rename(target)
    except OSError:
        if previous.exists():
            previous.rename(target)
        raise


def refresh_applet(backend):
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cosmic"
    app_id = "io.github.basanta_bhandari.NothingXApplet." + backend.title()
    for path in root.glob("com.system76.CosmicPanel.*/v1/plugins_*"):
        original = path.read_text()
        changed = re.sub(r'^\s*"' + re.escape(app_id) + r'",?\s*\n', "", original, flags=re.MULTILINE)
        if changed != original:
            path.write_text(changed)
            time.sleep(1.5)
            if path.read_text() == changed:
                path.write_text(original)


def apply(plan):
    backend, distribution = plan["backend"], plan["distribution"]
    if backend not in ("cpp", "rust") or distribution not in ("manual", "portable", "applet"):
        raise ValueError("Unknown update variant.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", plan["version"]):
        raise ValueError("Invalid release version.")
    artifact = Path(plan["artifact"])
    with artifact.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != plan["sha256"]:
            raise ValueError("The update file changed after download.")
    for attempt in range(120):
        try:
            os.kill(plan["parent"], 0)
        except ProcessLookupError:
            break
        time.sleep(.5)
    else:
        raise RuntimeError("The application did not close; the update was not applied.")
    root, source = Path(plan["root"]), Path(plan["source"])
    if distribution == "portable":
        if sys.platform == "darwin":
            result = subprocess.check_output(["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(artifact)])
            mount = next(Path(item["mount-point"]) for item in plistlib.loads(result)["system-entities"] if "mount-point" in item)
            try:
                apps = list(mount.glob("*.app"))
                if len(apps) != 1:
                    raise ValueError("The disk image must contain one app.")
                replace_app(apps[0], Path(plan["bundle"]))
            finally:
                run(["hdiutil", "detach", mount])
        else:
            if not plan.get("appimage"):
                raise ValueError("The current AppImage path is missing.")
            replace_file(artifact, Path(plan["appimage"]))
    elif distribution == "manual":
        remote = subprocess.check_output(["git", "-C", str(source), "remote", "get-url", "origin"], text=True).strip().removesuffix(".git").lower()
        if remote not in ("https://github.com/basanta-bhandari/nothing-x", "git@github.com:basanta-bhandari/nothing-x"):
            raise ValueError("The source checkout points to another repository.")
        if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
            raise ValueError("The source checkout has local changes. Commit or stash them before updating.")
        run(["git", "-C", source, "fetch", "origin", "tag", "v" + plan["version"]])
        commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "FETCH_HEAD^{commit}"], text=True).strip()
        if commit != plan["commit"]:
            raise ValueError("The release tag and manifest commit differ.")
        run(["git", "-C", source, "merge", "--ff-only", "FETCH_HEAD"])
        run([source / "setup.sh", "--backend", backend], cwd=source)
        if sys.platform == "darwin":
            label = "Cpp" if backend == "cpp" else "Rust"
            built = source / f"build/manual-{backend}/Nothing X {label}.app"
            if plan.get("bundle") and Path(plan["bundle"]) != built:
                replace_app(built, Path(plan["bundle"]))
        elif root != source:
            prefix = root.parents[1]
            run([source / ".venv/bin/python", source / "install-local.py", "--backend", backend, "--prefix", prefix])
    else:
        stage = artifact.parent / "unpacked"
        safe_extract(artifact, stage)
        package = stage / "NothingX"
        env = {**os.environ, "PYTHONPATH": str(package)}
        python = root / ".venv/bin/python"
        run([python, "-m", "pip", "install", "-r", package / "requirements.txt"], env=env)
        (package / ".venv/bin").mkdir(parents=True)
        (package / ".venv/bin/python").symlink_to(python)
        prefix = root.parents[1]
        run([python, package / "install-cosmic.py", "--backend", backend, "--prefix", prefix], cwd=package, env=env)
        refresh_applet(backend)
    restart(plan)
    print("Update complete.", flush=True)


def restart(plan):
    command = plan["restart"]
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("_PYI_") or key in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            env.pop(key, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    root = Path(plan["root"])
    working = root if plan["distribution"] != "portable" and root.exists() else Path.home()
    subprocess.Popen(command, cwd=working, env=env, start_new_session=True)


def main(arguments=None):
    arguments = arguments or sys.argv[1:]
    plan = json.loads(Path(arguments[0]).read_text())
    try:
        apply(plan)
    except Exception as error:
        print("Update failed:", error, flush=True)
        try:
            restart(plan)
        except OSError:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
