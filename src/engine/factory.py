"""
Engine factory.

Central dispatch from `settings.music_engine` to a concrete
`MusicEngineInterface` instance. Each engine is imported lazily so a
missing optional dependency (e.g. `musiclang_predict`) never breaks
other engines.

Supported values of `settings.music_engine`
-------------------------------------------
  "magenta"              -> MagentaEngine (the existing HTTP microservice).
  "musiclang"            -> MusicLangEngine (local Python; stub if
                            musiclang_predict is not installed).
  "anticipatory"         -> AnticipatoryEngine (local Python; stub if the
                            model is not installed).
  "composers_assistant"  -> ComposersAssistantEngine (CA2, MIT, multi-track
                            MIDI infilling; stub if not installed).
  "mmt"                  -> MMTEngine (Multitrack Music Transformer, MIT;
                            stub if not installed).
  "figaro"               -> FigaroEngine (description-conditioned, MIT;
                            stub if not installed).
  "null"                 -> NullEngine (explicit no-op; useful for CI + tests).
  "multi:a,b,..."        -> MultiEngine fanout over comma-separated engines.

Legacy call-sites `from src.engine.magenta_engine import create_engine`
continue to work — we re-export `create_engine` from magenta_engine for
backwards compatibility, but the real dispatch lives here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

from loguru import logger

from config.settings import settings
from src.engine.interface import MusicEngineInterface


# ---------------------------------------------------------------------------
# Reference-engine clone path auto-discovery (Round 2 Phase A)
# ---------------------------------------------------------------------------
# When users follow `colab_setup.ipynb` Step 5, reference engines are
# cloned to `/content/ref_engines/{figaro,mmt,composers-assistant-REAPER}`
# and the notebook adds those to `os.environ['PYTHONPATH']`. That env-var
# only lives in the notebook process — when the user later spawns a
# fresh shell (`/content/AI_Music# python -m src.main`), the engines can
# no longer be found.
#
# Fix: walk well-known clone locations at import time and prepend any
# that exist to `sys.path`, so the lazy import in each wrapper works
# regardless of how the server was launched. Also honour an explicit
# MG_REFERENCE_ENGINES_PATH env var as an override (os.pathsep-separated).

_DEFAULT_CLONE_ROOTS: tuple[Path, ...] = (
    Path("/content/ref_engines"),
    Path.cwd() / "ref_engines",
    Path(__file__).resolve().parent.parent.parent / "ref_engines",
    Path.home() / "ref_engines",
)

_CLONE_SUBDIRS: tuple[str, ...] = (
    # Each well-known clone target — both the parent dir and the clone
    # itself need to be on sys.path so `import figaro` finds the package
    # and inner imports resolve.
    "figaro",
    "mmt",
    "MMT-BERT",
    "composers-assistant-REAPER",
    "composers_assistant2",
    "composers_assistant",
)


def _inject_clone_paths() -> list[str]:
    """Prepend known reference-engine clone locations to `sys.path`.

    Returns the list of paths that were actually injected (for logging).
    Idempotent — paths already present are skipped.
    """
    injected: list[str] = []
    extra_roots: list[Path] = []
    if env := os.environ.get("MG_REFERENCE_ENGINES_PATH"):
        extra_roots.extend(
            Path(p) for p in env.split(os.pathsep) if p
        )
    candidates: list[Path] = []
    for root in (*extra_roots, *_DEFAULT_CLONE_ROOTS):
        if not root.is_dir():
            continue
        candidates.append(root)
        for sub in _CLONE_SUBDIRS:
            child = root / sub
            if child.is_dir():
                candidates.append(child)
    for path in candidates:
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)
            injected.append(s)
    return injected


_INJECTED_PATHS: list[str] = _inject_clone_paths()
if _INJECTED_PATHS:
    logger.debug(
        "[engine.factory] reference-engine clone paths injected: "
        + ", ".join(_INJECTED_PATHS)
    )


def create_engine(
    engine_spec: str | None = None,
    *,
    strategy: str = "first_healthy",
) -> MusicEngineInterface:
    """Build and return a music engine for the given spec.

    If `engine_spec` is None, reads `settings.music_engine`.

    Accepted spec forms
    -------------------
    - Single name: "magenta", "musiclang", "anticipatory",
      "composers_assistant", "mmt", "figaro", "null".
    - Comma list: "magenta,musiclang,mmt"  (auto-wrapped in MultiEngine).
    - Explicit multi: "multi:magenta,musiclang" (same effect).

    `strategy` is forwarded to MultiEngine when building a fanout.
    Default `"first_healthy"` preserves prior single-engine semantics;
    Round 2 Phase A passes `"merge"` to collect reference drafts.
    """
    spec = (engine_spec or settings.music_engine or "magenta").strip()

    # Multi-engine fanout: "multi:magenta,musiclang"
    if spec.startswith("multi:"):
        inner = spec.split(":", 1)[1]
        names = [s.strip() for s in inner.split(",") if s.strip()]
        return _build_multi(names, strategy=strategy)

    # Implicit multi: comma-separated names without "multi:" prefix.
    if "," in spec:
        names = [s.strip() for s in spec.split(",") if s.strip()]
        return _build_multi(names, strategy=strategy)

    return _build_single(spec)


def _build_single(name: str) -> MusicEngineInterface:
    name_l = name.lower()
    if name_l == "magenta":
        from src.engine.magenta_engine import MagentaEngine
        return MagentaEngine()
    if name_l in ("musiclang", "musiclang_predict"):
        try:
            from src.engine.musiclang_engine import MusicLangEngine
            return MusicLangEngine()
        except Exception as exc:
            logger.warning(
                "MusicLang engine unavailable ({}). Falling back to "
                "NullEngine.".format(exc)
            )
            from src.engine.null_engine import NullEngine
            return NullEngine(reason=f"musiclang import failed: {exc}")
    if name_l in ("anticipatory", "amt", "anticipatory_music_transformer"):
        try:
            from src.engine.anticipatory_engine import AnticipatoryEngine
            return AnticipatoryEngine()
        except Exception as exc:
            logger.warning(
                "Anticipatory engine unavailable ({}). Falling back to "
                "NullEngine.".format(exc)
            )
            from src.engine.null_engine import NullEngine
            return NullEngine(reason=f"anticipatory import failed: {exc}")
    if name_l in (
        "composers_assistant",
        "composers_assistant2",
        "ca2",
        "composers-assistant",
    ):
        try:
            from src.engine.composers_assistant_engine import (
                ComposersAssistantEngine,
            )
            return ComposersAssistantEngine()
        except Exception as exc:
            logger.warning(
                "Composer's Assistant 2 engine unavailable ({}). Falling "
                "back to NullEngine.".format(exc)
            )
            from src.engine.null_engine import NullEngine
            return NullEngine(
                reason=f"composers_assistant import failed: {exc}",
            )
    if name_l in ("mmt", "mmt_bert", "multitrack_music_transformer"):
        try:
            from src.engine.mmt_engine import MMTEngine
            return MMTEngine()
        except Exception as exc:
            logger.warning(
                "MMT engine unavailable ({}). Falling back to NullEngine."
                .format(exc)
            )
            from src.engine.null_engine import NullEngine
            return NullEngine(reason=f"mmt import failed: {exc}")
    if name_l in ("figaro", "figaro_midi", "figaro_model"):
        try:
            from src.engine.figaro_engine import FigaroEngine
            return FigaroEngine()
        except Exception as exc:
            logger.warning(
                "FIGARO engine unavailable ({}). Falling back to NullEngine."
                .format(exc)
            )
            from src.engine.null_engine import NullEngine
            return NullEngine(reason=f"figaro import failed: {exc}")
    if name_l in ("null", "none", "disabled"):
        from src.engine.null_engine import NullEngine
        return NullEngine(reason="explicitly disabled via settings")

    logger.warning(
        f"Unknown music_engine '{name}' — falling back to magenta."
    )
    from src.engine.magenta_engine import MagentaEngine
    return MagentaEngine()


def _build_multi(
    names: Iterable[str],
    *,
    strategy: str = "first_healthy",
) -> MusicEngineInterface:
    """Build a MultiEngine over the given engine names.

    Each underlying engine is built with `_build_single`, so a missing
    dependency degrades to NullEngine silently — the fanout survives.
    """
    from src.engine.multi_engine import MultiEngine
    engines = [_build_single(n) for n in names]
    return MultiEngine(engines=engines, strategy=strategy)


# ---------------------------------------------------------------------------
# Engine availability report (used by /api/health and src/main.py startup)
# ---------------------------------------------------------------------------

def engine_status_report(spec: str | None = None) -> dict[str, dict]:
    """Build a per-engine availability map for a given fanout spec.

    Returns
    -------
    dict mapping engine name -> {
        "type":      class name of the engine actually constructed
                     ("MagentaEngine", "MusicLangEngine", "NullEngine", ...).
        "available": bool — True when the wrapper imported its backend
                     and is NOT a NullEngine.
        "reason":    str — human-readable explanation when unavailable
                     (typically the original ImportError message).
    }

    No network calls; no model loads. Just attempts the lazy import each
    wrapper does in __init__ and reports the result. Safe to call from
    a startup hook, /api/health, or a one-shot CLI probe.

    `spec` may be the same value `create_engine` accepts (single name,
    comma-list, or "multi:..."). When None, reads
    `settings.reference_engines`.
    """
    raw = (spec or settings.reference_engines or "magenta").strip()
    if raw.startswith("multi:"):
        raw = raw.split(":", 1)[1]
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        names = ["magenta"]

    report: dict[str, dict] = {}
    for name in names:
        engine = _build_single(name)
        type_name = type(engine).__name__
        # NullEngine carries the failure reason in its `reason` attr.
        reason = getattr(engine, "reason", "") or ""
        report[name] = {
            "type": type_name,
            "available": type_name != "NullEngine",
            "reason": str(reason),
        }
        # Best-effort cleanup; engines that aren't async-aware skip this.
        close = getattr(engine, "close", None)
        if callable(close):
            try:
                import asyncio
                if asyncio.iscoroutinefunction(close):
                    # Don't block — only schedule if a loop is running.
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(close())
                    except RuntimeError:
                        pass
                else:
                    close()
            except Exception:
                pass
    return report


def format_engine_status(
    report: dict[str, dict],
    *,
    indent: str = "  ",
) -> str:
    """Render an engine_status_report() dict as a human log block."""
    if not report:
        return f"{indent}(no engines configured)"
    lines = []
    for name, info in report.items():
        mark = "✓" if info.get("available") else "✗"
        type_name = info.get("type", "?")
        if info.get("available"):
            lines.append(f"{indent}{mark} {name:22s} -> {type_name}")
        else:
            reason = info.get("reason", "").splitlines()[0] if info.get("reason") else ""
            tail = f" ({reason})" if reason else ""
            lines.append(
                f"{indent}{mark} {name:22s} -> {type_name}{tail}"
            )
    return "\n".join(lines)
