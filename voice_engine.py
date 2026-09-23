"""Priority 10: provider-based voice input routed through the text executor."""

from __future__ import annotations

import json
import queue
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class SpeechToTextProvider(ABC):
    @abstractmethod
    def start(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def listen_once(self) -> Dict[str, Any]:
        raise NotImplementedError


class VoskSTT(SpeechToTextProvider):
    """Offline streaming STT provider. Requires a locally downloaded Vosk model."""

    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.audio = None
        self.recognizer = None
        self.model = None
        self._load()

    def _load(self) -> None:
        try:
            import sounddevice as sd
            import vosk
        except ImportError as exc:
            raise RuntimeError("Install vosk and sounddevice for offline voice input") from exc
        self.audio = sd
        self.model = vosk.Model(self.model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)

    def start(self) -> Dict[str, Any]:
        return {"status": "ready", "provider": "vosk", "offline": True}

    def stop(self) -> Dict[str, Any]:
        return {"status": "stopped", "provider": "vosk"}

    def listen_once(self) -> Dict[str, Any]:
        audio_queue: queue.Queue[bytes] = queue.Queue()

        def callback(indata, frames, time_info, status):
            audio_queue.put(bytes(indata))

        try:
            with self.audio.RawInputStream(samplerate=self.sample_rate, blocksize=8000, dtype="int16", channels=1, callback=callback):
                while True:
                    if self.recognizer.AcceptWaveform(audio_queue.get()):
                        result = json.loads(self.recognizer.Result())
                        text = result.get("text", "").strip()
                        if text:
                            return {"status": "completed", "text": text, "confidence": 0.85, "provider": "vosk"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "provider": "vosk"}


class SpeechRecognitionSTT(SpeechToTextProvider):
    """Compatibility fallback for the existing microphone implementation."""

    def __init__(self, voice_input):
        self.voice_input = voice_input

    def start(self) -> Dict[str, Any]:
        available = self.voice_input.recognizer is not None and self.voice_input.microphone is not None
        return {"status": "ready" if available else "unavailable", "provider": "speech_recognition", "offline": False}

    def stop(self) -> Dict[str, Any]:
        return {"status": "stopped", "provider": "speech_recognition"}

    def listen_once(self) -> Dict[str, Any]:
        result = self.voice_input.listen_for_command(timeout=10)
        if result.get("status") == "completed":
            result.setdefault("confidence", 0.85)
            result.setdefault("provider", "speech_recognition")
        return result


class TextToSpeechProvider(ABC):
    @abstractmethod
    def speak(self, text: str) -> Dict[str, Any]:
        raise NotImplementedError


class WindowsTTS(TextToSpeechProvider):
    def __init__(self, engine=None):
        if engine is None:
            import pyttsx3
            engine = pyttsx3.init()
        self.engine = engine

    def speak(self, text: str) -> Dict[str, Any]:
        try:
            self.engine.say(text)
            self.engine.runAndWait()
            return {"status": "completed", "text": text}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}


class VoiceEngine:
    """Voice input state machine. Transcripts use the normal text command handler."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    UNDERSTANDING = "UNDERSTANDING"
    EXECUTING = "EXECUTING"
    RESPONDING = "RESPONDING"

    def __init__(self, stt: SpeechToTextProvider, tts: Optional[TextToSpeechProvider] = None, min_confidence: float = 0.65):
        self.stt = stt
        self.tts = tts
        self.min_confidence = min_confidence
        self.state = self.IDLE
        self.running = False
        self.last_transcript = ""
        self.command_handler: Optional[Callable[[str], Dict[str, Any]]] = None
        self.event_handler: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_command_handler(self, handler: Callable[[str], Dict[str, Any]]) -> None:
        self.command_handler = handler

    def set_event_handler(self, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        self.event_handler = handler

    def _emit(self, name: str, **payload: Any) -> None:
        if self.event_handler:
            self.event_handler(name, payload)

    def start(self) -> Dict[str, Any]:
        result = self.stt.start()
        if result.get("status") in {"ready", "started"}:
            self.running = True
            self.state = self.IDLE
            self._emit("voice.state", state=self.state)
            return {"status": "started", "provider": result.get("provider"), "offline": result.get("offline", False)}
        return result

    def stop(self) -> Dict[str, Any]:
        self.running = False
        self._stop_event.set()
        self.state = self.IDLE
        self._emit("voice.state", state=self.state)
        return self.stt.stop()

    def listen_and_execute(self) -> Dict[str, Any]:
        if self.command_handler is None:
            return {"status": "failed", "error": "command_handler_not_configured"}
        if not self.running:
            started = self.start()
            if started.get("status") != "started":
                return started
        self.state = self.LISTENING
        self._emit("voice.state", state=self.state)
        transcript = self.stt.listen_once()
        text = str(transcript.get("text", "")).strip()
        confidence = float(transcript.get("confidence", 0.0) or 0.0)
        self.last_transcript = text
        self._emit("voice.partial", text=text, confidence=confidence)
        if transcript.get("status") != "completed" or not text:
            self.state = self.IDLE
            self._emit("voice.state", state=self.state)
            return {"status": "failed", "error": transcript.get("error", "empty_transcript"), "transcript": text}
        if confidence < self.min_confidence:
            self.state = self.IDLE
            self._emit("voice.clarification", text=text, confidence=confidence)
            return {"status": "clarification_required", "message": f"Did you say: {text}?", "transcript": text, "confidence": confidence}
        self.state = self.UNDERSTANDING
        self._emit("voice.state", state=self.state)
        self.state = self.EXECUTING
        self._emit("voice.state", state=self.state)
        result = self.command_handler(text)
        self.state = self.RESPONDING
        self._emit("voice.state", state=self.state)
        response = self._response_for(result)
        if self.tts and response:
            self.tts.speak(response)
        self.state = self.IDLE
        self._emit("voice.state", state=self.state)
        return {"status": "completed", "transcript": text, "confidence": confidence, "execution": result, "response": response}

    def start_live(self, status_handler: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        if self._thread and self._thread.is_alive():
            return {"status": "already_running"}
        started = self.start()
        if started.get("status") != "started":
            return started
        self._stop_event.clear()

        def loop():
            while self.running and not self._stop_event.is_set():
                result = self.listen_and_execute()
                if status_handler:
                    status_handler(result.get("response", result.get("message", result.get("status", "unknown"))))
            self.state = self.IDLE

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return {"status": "started", "provider": started.get("provider")}

    def _response_for(self, result: Dict[str, Any]) -> str:
        status = result.get("status")
        if status == "completed":
            return "Done."
        if status == "clarification_required":
            return result.get("message", "Please clarify the command.")
        return result.get("message", result.get("error", "The command could not be completed."))
