"""Trusted local input loaders for optional-runtime smoke commands."""

from __future__ import annotations

import importlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any


def load_json_file(path: Path, *, name: str) -> object:
    """Load a JSON file for a smoke input surface."""

    try:
        return json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{name} file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{name} file is not valid JSON: {path}: {exc}") from exc


def load_json_object(path: Path, *, name: str) -> dict[str, Any]:
    """Load a JSON file and require an object payload."""

    payload = load_json_file(path, name=name)
    if not isinstance(payload, dict):
        raise SystemExit(f"{name} must decode to a JSON object.")
    return dict(payload)


def code_opt_in_message(
    name: str,
    *,
    flag: str,
    trusted_label: str | None = None,
) -> str:
    """Return the standard local-code execution opt-in message."""

    label = trusted_label or f"{name} code"
    return (
        f"Loading {name} imports and executes local Python code; pass {flag} only for "
        f"trusted {label}."
    )


def require_code_allowed(
    *,
    name: str,
    allow_code: bool,
    flag: str,
    trusted_label: str | None = None,
    message: str | None = None,
) -> None:
    """Require an explicit opt-in before importing local trusted code."""

    if not allow_code:
        raise SystemExit(
            message or code_opt_in_message(name, flag=flag, trusted_label=trusted_label)
        )


def module_from_path(
    path: Path,
    *,
    name: str = "Python module",
    allow_code: bool = True,
    flag: str = "--allow-code",
    trusted_label: str | None = None,
    opt_in_message: str | None = None,
) -> ModuleType:
    """Load a Python module from a trusted local file path."""

    require_code_allowed(
        name=name,
        allow_code=allow_code,
        flag=flag,
        trusted_label=trusted_label,
        message=opt_in_message,
    )
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Python module file does not exist: {path}")
    module_spec = importlib.util.spec_from_file_location(resolved.stem, resolved)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"Could not load Python module from: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def callable_spec_parts(spec: str, *, name: str) -> tuple[str, str]:
    """Split a module_or_file:function callable spec."""

    if ":" not in spec:
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    module_ref, function_name = spec.rsplit(":", 1)
    if not module_ref.strip() or not function_name.strip():
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    return module_ref, function_name


def looks_like_module_path(module_ref: str) -> bool:
    """Return whether a callable module reference points at a local file path."""

    return Path(module_ref).exists() or module_ref.endswith(".py") or "/" in module_ref


def load_callable_module(
    module_ref: str,
    *,
    name: str,
    allow_code: bool = True,
    flag: str = "--allow-code",
    trusted_label: str | None = None,
    require_code: bool = False,
) -> ModuleType:
    """Load the module side of a trusted callable spec."""

    if require_code:
        require_code_allowed(
            name=name,
            allow_code=allow_code,
            flag=flag,
            trusted_label=trusted_label,
        )
    if looks_like_module_path(module_ref):
        return module_from_path(
            Path(module_ref),
            name=name,
            allow_code=allow_code,
            flag=flag,
            trusted_label=trusted_label,
        )
    try:
        return importlib.import_module(module_ref)
    except ImportError as exc:
        raise SystemExit(f"Could not import {name} module '{module_ref}': {exc}") from exc


def callable_attribute(module: ModuleType, function_name: str, *, name: str) -> Callable[..., Any]:
    """Return a callable module attribute with a smoke-facing error message."""

    try:
        loaded = getattr(module, function_name)
    except AttributeError as exc:
        raise SystemExit(f"{name} function '{function_name}' was not found.") from exc
    if not callable(loaded):
        raise SystemExit(f"{name} target '{function_name}' is not callable.")
    return loaded


def load_callable(
    spec: str,
    *,
    name: str,
    allow_code: bool = True,
    flag: str = "--allow-code",
    trusted_label: str | None = None,
    require_code: bool = False,
) -> Callable[..., Any]:
    """Load a trusted callable from a module_or_file:function spec."""

    if require_code:
        require_code_allowed(
            name=name,
            allow_code=allow_code,
            flag=flag,
            trusted_label=trusted_label,
        )
    module_ref, function_name = callable_spec_parts(spec, name=name)
    module = load_callable_module(
        module_ref,
        name=name,
        allow_code=allow_code,
        flag=flag,
        trusted_label=trusted_label,
        require_code=False,
    )
    return callable_attribute(module, function_name, name=name)
