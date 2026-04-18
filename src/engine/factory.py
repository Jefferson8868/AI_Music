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

from typing import Iterable

from loguru import logger

from config.settings import settings
from src.engine.interface import MusicEngineInterface


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
