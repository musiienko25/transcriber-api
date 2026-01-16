"""ASR (Automatic Speech Recognition) service using Faster-Whisper."""

import asyncio
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ModelNotAvailableError, TranscriptionFailedError
from app.core.logging import get_logger
from app.models.responses import TranscriptionSegment, TranscriptionSource

logger = get_logger(__name__)

# Global model instance (lazy loaded)
_whisper_model = None
_model_lock = asyncio.Lock()


class ASRService:
    """Service for speech recognition using Faster-Whisper."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    async def get_model(self) -> Any:
        """Get or initialize the Whisper model (lazy loading)."""
        global _whisper_model

        if _whisper_model is not None:
            return _whisper_model

        async with _model_lock:
            # Double-check after acquiring lock
            if _whisper_model is not None:
                return _whisper_model

            logger.info(
                "Loading Whisper model",
                model=self.settings.whisper_model,
                device=self.settings.whisper_device,
            )

            try:
                from faster_whisper import WhisperModel

                # Determine device
                device = self.settings.whisper_device
                if device == "auto":
                    try:
                        import torch
                        device = "cuda" if torch.cuda.is_available() else "cpu"
                    except ImportError:
                        device = "cpu"

                # Determine compute type
                compute_type = self.settings.whisper_compute_type
                if compute_type == "auto":
                    compute_type = "float16" if device == "cuda" else "int8"

                # Load model in thread pool
                loop = asyncio.get_event_loop()
                _whisper_model = await loop.run_in_executor(
                    None,
                    lambda: WhisperModel(
                        self.settings.whisper_model,
                        device=device,
                        compute_type=compute_type,
                    ),
                )

                logger.info(
                    "Whisper model loaded",
                    model=self.settings.whisper_model,
                    device=device,
                    compute_type=compute_type,
                )

                return _whisper_model

            except Exception as e:
                logger.error("Failed to load Whisper model", error=str(e))
                raise ModelNotAvailableError(self.settings.whisper_model)

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        translate_to: str | None = None,
        diarise: bool = False,
    ) -> tuple[list[TranscriptionSegment], str, float, float, list[str]]:
        """
        Transcribe audio file using Whisper.

        Args:
            audio_path: Path to audio file
            language: Source language hint (optional, auto-detected if not provided)
            translate_to: Target language for translation (optional)
            diarise: Enable speaker diarisation (not yet implemented)

        Returns:
            Tuple of (segments, detected_language, confidence, duration, warnings)

        Raises:
            TranscriptionFailedError: If transcription fails
        """
        warnings: list[str] = []

        if diarise:
            warnings.append("Speaker diarisation requested but not yet implemented")

        try:
            model = await self.get_model()

            logger.info(
                "Starting transcription",
                path=str(audio_path),
                language=language,
            )

            # Run transcription in thread pool
            loop = asyncio.get_event_loop()

            # Determine task (transcribe or translate)
            task = "transcribe"
            if translate_to == "en" and language != "en":
                task = "translate"
                warnings.append(f"Translating to English using Whisper's built-in translation")

            def do_transcribe() -> tuple:
                segments_gen, info = model.transcribe(
                    str(audio_path),
                    language=language,
                    task=task,
                    beam_size=5,
                    word_timestamps=False,
                    vad_filter=True,  # Voice activity detection
                    vad_parameters=dict(
                        min_silence_duration_ms=500,
                    ),
                )
                # Convert generator to list
                return list(segments_gen), info

            raw_segments, info = await loop.run_in_executor(None, do_transcribe)

            # Extract info
            detected_language = info.language
            duration = info.duration
            confidence = info.language_probability

            # Convert to our segment format
            segments = []
            for seg in raw_segments:
                segment = TranscriptionSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=seg.avg_logprob if hasattr(seg, "avg_logprob") else None,
                )
                segments.append(segment)

            logger.info(
                "Transcription completed",
                path=str(audio_path),
                language=detected_language,
                duration=duration,
                segments_count=len(segments),
                confidence=confidence,
            )

            return segments, detected_language, confidence, duration, warnings

        except ModelNotAvailableError:
            raise
        except Exception as e:
            logger.error("Transcription failed", path=str(audio_path), error=str(e))
            raise TranscriptionFailedError(str(e), "local")

    async def transcribe_with_openai(
        self,
        audio_path: Path,
        language: str | None = None,
    ) -> tuple[list[TranscriptionSegment], str, float, float, list[str]]:
        """
        Transcribe using OpenAI's Whisper API.

        Args:
            audio_path: Path to audio file
            language: Source language hint

        Returns:
            Tuple of (segments, detected_language, confidence, duration, warnings)
        """
        import httpx

        if not self.settings.openai_api_key:
            raise TranscriptionFailedError("OpenAI API key not configured", "openai")

        warnings: list[str] = []

        try:
            logger.info("Transcribing with OpenAI", path=str(audio_path))

            async with httpx.AsyncClient() as client:
                with open(audio_path, "rb") as f:
                    files = {"file": (audio_path.name, f, "audio/mpeg")}
                    data = {
                        "model": "whisper-1",
                        "response_format": "verbose_json",
                    }
                    if language:
                        data["language"] = language

                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                        files=files,
                        data=data,
                        timeout=300.0,
                    )

                    if response.status_code != 200:
                        raise TranscriptionFailedError(
                            f"OpenAI API error: {response.text}", "openai"
                        )

                    result = response.json()

            # Parse response
            detected_language = result.get("language", language or "en")
            duration = result.get("duration", 0.0)

            segments = []
            for seg in result.get("segments", []):
                segment = TranscriptionSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"].strip(),
                )
                segments.append(segment)

            # If no segments, create one from full text
            if not segments and result.get("text"):
                segments = [
                    TranscriptionSegment(
                        start=0.0,
                        end=duration,
                        text=result["text"].strip(),
                    )
                ]

            logger.info(
                "OpenAI transcription completed",
                language=detected_language,
                duration=duration,
                segments_count=len(segments),
            )

            return segments, detected_language, 0.95, duration, warnings

        except TranscriptionFailedError:
            raise
        except Exception as e:
            logger.error("OpenAI transcription failed", error=str(e))
            raise TranscriptionFailedError(str(e), "openai")

    async def get_audio_duration(self, audio_path: Path) -> float:
        """Get duration of audio file in seconds."""
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def get_duration() -> float:
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        str(audio_path),
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return float(result.stdout.strip())
                return 0.0

            return await loop.run_in_executor(None, get_duration)

        except Exception as e:
            logger.warning("Could not get audio duration", error=str(e))
            return 0.0

    def get_source(self) -> TranscriptionSource:
        """Get the transcription source based on provider."""
        provider = self.settings.asr_provider
        return {
            "local": TranscriptionSource.ASR_LOCAL,
            "openai": TranscriptionSource.ASR_OPENAI,
            "deepgram": TranscriptionSource.ASR_DEEPGRAM,
            "assemblyai": TranscriptionSource.ASR_ASSEMBLYAI,
        }.get(provider, TranscriptionSource.ASR)
