"""Celery task for generating notebook audio overviews."""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.core.config import get_app_config, get_settings
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.modules.audio_overviews.repository import get_audio_overview_repository
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)

MIN_SCRIPT_WORDS = 460
MAX_CONTEXT_CHARS = 42000
BATCH_CONTEXT_CHARS = 6000
MAX_RENDER_ATTEMPTS = 3
AUDIO_RATE = 24000


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_audio_overview_task(
    self,
    overview_id: str,
    notebook_id: str,
    user_id: str,
    document_names: list[str],
) -> dict[str, Any]:
    """Generate a grounded transcript, render TTS audio, and upload an M4A file."""
    settings = get_settings()
    app_config = get_app_config()
    client = get_supabase_client()
    repository = get_audio_overview_repository(client)
    document_repository = get_document_repository(client)
    genai_client = genai.Client(api_key=settings.google_api_key)

    repository.update_status(overview_id, "processing", {"error_message": None})

    try:
        chunks = document_repository.get_all_chunks_by_names(document_names, notebook_id)
        if not chunks:
            raise ValueError("No indexed chunks were found for the selected documents.")

        context = _build_context(chunks)
        if len(context) > MAX_CONTEXT_CHARS:
            context = _summarize_context(genai_client, app_config.llm.gemini.model, context, document_names)

        script_payload = _generate_script(
            genai_client=genai_client,
            model=app_config.llm.gemini.model,
            context=context,
            document_names=document_names,
            previous_script=None,
        )

        with tempfile.TemporaryDirectory(prefix="datn-audio-overview-") as temp_dir:
            workspace = Path(temp_dir)
            duration_seconds = 0.0
            m4a_path = workspace / "overview.m4a"

            for attempt in range(MAX_RENDER_ATTEMPTS):
                wav_path = workspace / f"overview-{attempt}.wav"
                m4a_path = workspace / f"overview-{attempt}.m4a"
                _render_tts_to_wav(
                    genai_client=genai_client,
                    tts_model=settings.audio_overview_tts_model,
                    script_payload=script_payload,
                    wav_path=wav_path,
                )
                _encode_m4a(wav_path, m4a_path)
                duration_seconds = _probe_duration(m4a_path)
                if duration_seconds >= settings.audio_overview_min_duration_seconds:
                    break
                if attempt < MAX_RENDER_ATTEMPTS - 1:
                    script_payload = _generate_script(
                        genai_client=genai_client,
                        model=app_config.llm.gemini.model,
                        context=context,
                        document_names=document_names,
                        previous_script=script_payload.get("script_text"),
                    )

            storage_path = f"{user_id}/{notebook_id}/{overview_id}.m4a"
            _upload_audio(client, settings.audio_overview_bucket, storage_path, m4a_path)

        metadata = {
            "document_names": document_names,
            "task_id": self.request.id,
            "title": script_payload.get("title") or "Audio Overview",
            "style": script_payload.get("style") or "podcast_dialogue",
            "script_text": script_payload["script_text"],
            "speakers": script_payload.get("speakers") or [],
            "duration_seconds": duration_seconds,
            "content_type": "audio/mp4",
            "error_message": None,
            "script_model": app_config.llm.gemini.model,
            "tts_model": settings.audio_overview_tts_model,
        }
        repository.update_status(overview_id, "completed", metadata, storage_path=storage_path)
        return {
            "overview_id": overview_id,
            "status": "completed",
            "duration_seconds": duration_seconds,
            "storage_path": storage_path,
        }
    except Exception as exc:
        logger.exception("Audio overview generation failed overview_id=%s notebook_id=%s", overview_id, notebook_id)
        repository.update_status(
            overview_id,
            "failed",
            {
                "document_names": document_names,
                "task_id": self.request.id,
                "error_message": str(exc),
            },
        )
        raise


def _build_context(chunks: list[dict[str, Any]]) -> str:
    """Format document chunks into a compact source context."""
    parts: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        document = chunk.get("document_name", "unknown")
        page_range = chunk.get("page_range") or "unknown"
        content = re.sub(r"\s+", " ", str(chunk.get("content", ""))).strip()
        if not content:
            continue
        parts.append(f"[Source {index}] Document: {document}; pages: {page_range}\n{content}")
    return "\n\n".join(parts)


def _summarize_context(genai_client: genai.Client, model: str, context: str, document_names: list[str]) -> str:
    """Summarize long notebook context in batches before final script generation."""
    summaries: list[str] = []
    for batch in _split_text(context, BATCH_CONTEXT_CHARS):
        prompt = (
            "Summarize this document context for a grounded audio overview. "
            "Keep important claims, definitions, numbers, caveats, and relationships. "
            "Do not add facts that are not present.\n\n"
            f"Selected documents: {', '.join(document_names)}\n\n"
            f"Context:\n{batch}"
        )
        response = genai_client.models.generate_content(model=model, contents=prompt)
        summaries.append(str(response.text or "").strip())
    return "\n\n".join(summary for summary in summaries if summary)


def _generate_script(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    previous_script: str | None,
) -> dict[str, Any]:
    """Generate a podcast/news transcript as structured JSON."""
    retry_instruction = ""
    if previous_script:
        retry_instruction = (
            "\nThe previous transcript was too short for a 2 minute 30 second audio. "
            "Expand it substantially while preserving factual grounding. "
            "Previous transcript:\n"
            f"{previous_script}\n"
        )

    prompt = f"""
You are creating an Audio Overview for a research notebook.

Use only the supplied context. Choose the best style:
- "podcast_dialogue" when the material benefits from a two-host explanatory conversation.
- "news_briefing" when the material is sparse, formal, or better delivered as a concise bulletin.

Requirements:
- Auto-detect the main language from the context and write in that language.
- The spoken transcript must be at least {MIN_SCRIPT_WORDS} words so the rendered audio can reach at least 2 minutes 30 seconds at a natural pace.
- If the documents are sparse, fill time with careful framing, definitions, implications, recap, and transitions, but do not invent unsupported facts.
- For podcast_dialogue, use exactly two speaker names and write each line as "Speaker: text".
- For news_briefing, use one speaker name and write it as "Speaker: text".
- Return only valid JSON with keys: style, title, speakers, script_text.

Selected documents: {", ".join(document_names)}
{retry_instruction}
Context:
{context}
""".strip()

    response = genai_client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.45,
            max_output_tokens=7000,
            response_mime_type="application/json",
        ),
    )
    payload = _parse_json_object(str(response.text or ""))
    script_text = str(payload.get("script_text") or "").strip()
    if not script_text:
        raise ValueError("Gemini did not return an audio script.")

    speakers = payload.get("speakers")
    if not isinstance(speakers, list) or not speakers:
        speakers = ["Host A", "Host B"] if payload.get("style") == "podcast_dialogue" else ["Anchor"]

    return {
        "style": str(payload.get("style") or "podcast_dialogue"),
        "title": str(payload.get("title") or "Audio Overview"),
        "speakers": [str(speaker) for speaker in speakers[:2]],
        "script_text": script_text,
    }


def _render_tts_to_wav(
    *,
    genai_client: genai.Client,
    tts_model: str,
    script_payload: dict[str, Any],
    wav_path: Path,
) -> None:
    """Render Gemini TTS PCM bytes into a WAV file."""
    speakers = [str(speaker) for speaker in script_payload.get("speakers", []) if str(speaker).strip()]
    script_text = str(script_payload["script_text"])
    tts_prompt = (
        "Read the following transcript naturally for a research audio overview. "
        "Keep a clear academic tone and preserve the speaker labels only as performance direction.\n\n"
        f"{script_text}"
    )

    if script_payload.get("style") == "podcast_dialogue" and len(speakers) >= 2:
        speech_config = types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker=speakers[0],
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker=speakers[1],
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                        ),
                    ),
                ]
            )
        )
    else:
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
            )
        )

    response = genai_client.models.generate_content(
        model=tts_model,
        contents=tts_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=speech_config,
        ),
    )
    inline_data = response.candidates[0].content.parts[0].inline_data
    audio_bytes = _coerce_audio_bytes(inline_data.data)
    _write_wave(wav_path, audio_bytes)


def _coerce_audio_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)


def _write_wave(path: Path, pcm: bytes, channels: int = 1, rate: int = AUDIO_RATE, sample_width: int = 2) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(rate)
        wav.writeframes(pcm)


def _encode_m4a(wav_path: Path, m4a_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to encode Audio Overview files as M4A.")

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", "96k", str(m4a_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "ffmpeg returned no output.").strip()
        raise RuntimeError(f"ffmpeg failed to encode M4A: {details}")


def _probe_duration(audio_path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _upload_audio(client: Any, bucket: str, storage_path: str, audio_path: Path) -> None:
    file_options = {"content-type": "audio/mp4"}
    with audio_path.open("rb") as file:
        try:
            client.storage.from_(bucket).update(storage_path, file, file_options=file_options)
        except Exception:
            file.seek(0)
            client.storage.from_(bucket).upload(storage_path, file, file_options=file_options)


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from Gemini.")
    return parsed


def _split_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
