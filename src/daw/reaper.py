"""
Reaper DAW Integration Layer
Communicates with Reaper via its ReaScript/HTTP control surface
to create tracks, insert MIDI, load VST plugins, and control transport.
"""

from __future__ import annotations

import httpx
from loguru import logger
from pathlib import Path

from src.music.models import Arrangement, Track


class ReaperClient:
    """
    Client for controlling Reaper DAW via the built-in web interface
    or a custom HTTP/OSC bridge.

    Reaper must have the web control surface enabled:
    Preferences → Control/OSC/Web → Add → Web browser interface
    """

    def __init__(self, host: str = "localhost", port: int = 9090):
        self.base_url = f"http://{host}:{port}"
        self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def is_connected(self) -> bool:
        try:
            resp = await self._http.get(f"{self.base_url}/;transport")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    async def play(self) -> None:
        await self._action(1007)

    async def stop(self) -> None:
        await self._action(1016)

    async def record(self) -> None:
        await self._action(1013)

    async def goto_start(self) -> None:
        await self._action(40042)

    async def set_tempo(self, bpm: float) -> None:
        await self._command(f"SET/TEMPO/{bpm}")

    # ------------------------------------------------------------------
    # Track operations
    # ------------------------------------------------------------------

    async def insert_track(self, name: str, index: int = -1) -> int:
        """Insert a new track. Returns the track index."""
        await self._action(40001)  # Insert new track
        if name:
            await self._command(f"SET/TRACK/{index if index >= 0 else 'LAST'}/NAME/{name}")
        return index

    async def set_track_instrument(self, track_index: int, vst_name: str) -> None:
        """Load a VST plugin on a track's FX chain."""
        await self._command(f"SET/TRACK/{track_index}/FX/ADD/{vst_name}")

    async def import_midi_to_track(self, track_index: int, midi_path: str | Path) -> None:
        """Import a MIDI file onto a specific track."""
        await self._command(f"SET/TRACK/{track_index}/MIDI/IMPORT/{midi_path}")

    # ------------------------------------------------------------------
    # Full arrangement deployment
    # ------------------------------------------------------------------

    async def deploy_arrangement(self, arrangement: Arrangement, midi_dir: Path) -> None:
        """
        Deploy a complete arrangement to Reaper:
        1. Set tempo and time signature
        2. Create tracks for each instrument
        3. Import MIDI for each track
        4. Load VST plugins where specified
        """
        if not await self.is_connected():
            logger.warning("Reaper is not connected. Skipping deployment.")
            return

        logger.info(f"Deploying arrangement '{arrangement.title}' to Reaper...")

        await self.goto_start()
        await self.set_tempo(arrangement.tempo)

        for i, track in enumerate(arrangement.tracks):
            await self.insert_track(track.name, i)

            midi_file = midi_dir / f"{track.name}.mid"
            if midi_file.exists():
                await self.import_midi_to_track(i, midi_file)

            if track.vst_plugin:
                await self.set_track_instrument(i, track.vst_plugin)

        logger.info("Arrangement deployed to Reaper.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _action(self, action_id: int) -> None:
        try:
            await self._http.get(f"{self.base_url}/;{action_id}")
        except Exception as e:
            logger.warning(f"Reaper action {action_id} failed: {e}")

    async def _command(self, cmd: str) -> None:
        try:
            await self._http.get(f"{self.base_url}/;{cmd}")
        except Exception as e:
            logger.warning(f"Reaper command '{cmd}' failed: {e}")
