from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app_info import APP_NAME


RuntimeProgress = Callable[[str], None]


@dataclass
class RuntimeActivation:
    selected: str
    active: bool
    site_packages: Path | None = None
    message: str = ""


def app_data_dir() -> Path:
    override = os.environ.get("WHISPER_BATCH_APPDATA")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def runtime_config_path() -> Path:
    return app_data_dir() / "runtime.json"


def runtime_root(flavor: str) -> Path:
    return app_data_dir() / "runtimes" / flavor


def runtime_site_packages(flavor: str) -> Path:
    return runtime_root(flavor) / "site-packages"


def runtime_marker_path(flavor: str) -> Path:
    return runtime_root(flavor) / "runtime-installed.json"


def get_selected_runtime() -> str:
    try:
        data = json.loads(runtime_config_path().read_text(encoding="utf-8"))
    except Exception:
        return "bundled"
    selected = str(data.get("selected", "bundled")).lower()
    return selected if selected in {"bundled", "cuda"} else "bundled"


def set_selected_runtime(flavor: str) -> None:
    normalized = flavor.lower()
    if normalized not in {"bundled", "cuda"}:
        raise ValueError(f"Unsupported runtime: {flavor}")
    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"selected": normalized}, indent=2), encoding="utf-8")


def is_runtime_installed(flavor: str) -> bool:
    return runtime_marker_path(flavor).exists() and runtime_site_packages(flavor).exists()


def _prepend_runtime_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def _add_dll_path(path: Path) -> None:
    if not path.exists():
        return
    os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(path))
        except OSError:
            pass


def activate_selected_runtime() -> RuntimeActivation:
    selected = get_selected_runtime()
    if selected == "bundled":
        return RuntimeActivation(selected=selected, active=False, message="Using bundled runtime")

    if not is_runtime_installed(selected):
        return RuntimeActivation(
            selected=selected,
            active=False,
            message=f"Selected {selected} runtime is not installed",
        )

    site_packages = runtime_site_packages(selected)
    _prepend_runtime_path(site_packages)
    _add_dll_path(site_packages / "torch" / "lib")
    return RuntimeActivation(
        selected=selected,
        active=True,
        site_packages=site_packages,
        message=f"Using {selected} runtime: {site_packages}",
    )


def install_runtime(flavor: str, progress: RuntimeProgress | None = None) -> None:
    normalized = flavor.lower()
    if normalized != "cuda":
        raise ValueError("Only the CUDA runtime can be installed after app installation.")

    emit = progress or (lambda _message: None)
    root = runtime_root(normalized)
    target = runtime_site_packages(normalized)
    staging = runtime_root(normalized + "-installing")

    emit("Preparing CUDA runtime install directory...")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        _pip_install_target(
            staging,
            [
                "torch",
                "--index-url",
                "https://download.pytorch.org/whl/cu126",
            ],
            emit,
        )

        if target.exists():
            emit("Replacing previous CUDA runtime...")
            shutil.rmtree(target)
        root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(target))
        runtime_marker_path(normalized).write_text(
            json.dumps({"flavor": normalized, "torch_index": "cu126"}, indent=2),
            encoding="utf-8",
        )
        set_selected_runtime(normalized)
        emit("CUDA runtime installed. Restart the app to use it.")
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _pip_install_target(target: Path, packages: list[str], emit: RuntimeProgress) -> None:
    args = ["install", "--upgrade", "--force-reinstall", "--target", str(target), *packages]
    emit("Downloading and installing CUDA PyTorch. This can take several minutes.")

    if getattr(sys, "frozen", False):
        try:
            from pip._internal.cli.main import main as pip_main
        except Exception as exc:
            raise RuntimeError("pip is not bundled with this app, so CUDA runtime installation is unavailable.") from exc
        result = pip_main(args)
        if result != 0:
            raise RuntimeError(f"pip failed with exit code {result}")
        return

    process = subprocess.Popen(
        [sys.executable, "-m", "pip", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        stripped = line.strip()
        if stripped:
            emit(stripped)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"pip failed with exit code {return_code}")
