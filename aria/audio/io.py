"""Full-duplex local audio: stream the mic up, play Aria's voice down.

``sounddevice`` (and its PortAudio dependency) is imported lazily inside
``start`` so the rest of the package — and the ``--simulate`` demo — imports and
runs on machines without an audio stack.

Phase 0 assumes headphones (confirmed with the user), so there is no acoustic
echo path and we don't need acoustic echo cancellation here. The one piece of
barge-in audio handling we do need is instant playback flush: when the user
talks over Aria, ``stop_playback`` drops every queued output sample so she goes
quiet immediately.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable

InputCallback = Callable[[bytes], Awaitable[None]]


class AudioIO:
    def __init__(self, sample_rate: int = 24_000, channels: int = 1, frame_ms: int = 40) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self._out_buf = bytearray()
        self._lock = threading.Lock()
        self._in_stream = None
        self._out_stream = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_input: InputCallback | None = None

    async def start(self, on_input_frame: InputCallback) -> None:
        import sounddevice as sd  # lazy: requires PortAudio

        self._loop = asyncio.get_running_loop()
        self._on_input = on_input_frame

        def in_cb(indata, frames, time_info, status) -> None:  # runs on PortAudio thread
            if self._on_input is None or self._loop is None:
                return
            data = bytes(indata)
            # Hand the frame to the asyncio loop without blocking the audio thread.
            asyncio.run_coroutine_threadsafe(self._on_input(data), self._loop)

        def out_cb(outdata, frames, time_info, status) -> None:  # runs on PortAudio thread
            need = frames * 2 * self.channels
            with self._lock:
                take = bytes(self._out_buf[:need])
                del self._out_buf[:need]
            if len(take) < need:  # underrun -> pad with silence
                take += b"\x00" * (need - len(take))
            outdata[:] = take

        self._in_stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frame_samples,
            callback=in_cb,
        )
        self._out_stream = sd.RawOutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frame_samples,
            callback=out_cb,
        )
        self._in_stream.start()
        self._out_stream.start()

    def play(self, pcm16: bytes) -> None:
        with self._lock:
            self._out_buf.extend(pcm16)

    def stop_playback(self) -> None:
        """Barge-in: drop all queued output so Aria stops talking immediately."""
        with self._lock:
            self._out_buf.clear()

    async def stop(self) -> None:
        for stream in (self._in_stream, self._out_stream):
            if stream is not None:
                stream.stop()
                stream.close()
        self._in_stream = self._out_stream = None
