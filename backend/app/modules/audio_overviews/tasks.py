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
    client = get_supabase_client()
    repository = get_audio_overview_repository(client)
    document_repository = get_document_repository(client)
    if not repository.get(overview_id):
        logger.info("Audio overview task skipped because overview no longer exists overview_id=%s", overview_id)
        return _cancelled_result(overview_id, "missing")

    app_config = get_app_config()
    audio_config = app_config.audio_overview
    genai_client = genai.Client(api_key=settings.google_api_key)

    try:
        repository.update_status(overview_id, "processing", {"error_message": None})
    except ValueError as exc:
        if _is_missing_overview_error(exc):
            logger.info("Audio overview task skipped because overview no longer exists overview_id=%s", overview_id)
            return _cancelled_result(overview_id, "missing")
        raise

    uploaded_storage_path: str | None = None
    try:
        chunks = document_repository.get_all_chunks_by_names(document_names, notebook_id)
        if not chunks:
            raise ValueError("No indexed chunks were found for the selected documents.")

        context = _build_context(chunks)
        if len(context) > audio_config.max_context_chars:
            context = _summarize_context(
                genai_client,
                app_config.llm.gemini.model,
                context,
                document_names,
                audio_config.batch_context_chars,
            )

        script_payload = _generate_script(
            genai_client=genai_client,
            model=app_config.llm.gemini.model,
            audio_config=audio_config,
            context=context,
            document_names=document_names,
            previous_script=None,
        )

        with tempfile.TemporaryDirectory(prefix="datn-audio-overview-") as temp_dir:
            workspace = Path(temp_dir)
            duration_seconds = 0.0
            m4a_path = workspace / "overview.m4a"
            max_render_attempts = max(1, int(audio_config.max_render_attempts))

            for attempt in range(max_render_attempts):
                wav_path = workspace / f"overview-{attempt}.wav"
                m4a_path = workspace / f"overview-{attempt}.m4a"
                _render_tts_to_wav(
                    genai_client=genai_client,
                    tts_model=audio_config.tts_model,
                    audio_config=audio_config,
                    script_payload=script_payload,
                    wav_path=wav_path,
                )
                _encode_m4a(
                    wav_path,
                    m4a_path,
                    audio_config.encode_bitrate,
                    audio_config.encode_timeout_seconds,
                )
                duration_seconds = _probe_duration(m4a_path, audio_config.probe_timeout_seconds)
                if duration_seconds >= audio_config.min_duration_seconds:
                    break
                if attempt < max_render_attempts - 1:
                    script_payload = _generate_script(
                        genai_client=genai_client,
                        model=app_config.llm.gemini.model,
                        audio_config=audio_config,
                        context=context,
                        document_names=document_names,
                        previous_script=script_payload.get("script_text"),
                    )

            _require_min_duration(duration_seconds, audio_config.min_duration_seconds)

            storage_path = f"{user_id}/{notebook_id}/{overview_id}.m4a"
            if not repository.get(overview_id):
                logger.info("Audio overview task cancelled before upload overview_id=%s", overview_id)
                return _cancelled_result(overview_id, "deleted")

            _upload_audio(client, settings.audio_overview_bucket, storage_path, m4a_path)
            uploaded_storage_path = storage_path

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
            "tts_model": audio_config.tts_model,
        }
        try:
            repository.update_status(overview_id, "completed", metadata, storage_path=storage_path)
        except ValueError as exc:
            if _is_missing_overview_error(exc):
                _remove_uploaded_audio(client, settings.audio_overview_bucket, uploaded_storage_path)
                logger.info("Audio overview task finished after overview was deleted overview_id=%s", overview_id)
                return _cancelled_result(overview_id, "deleted")
            raise
        return {
            "overview_id": overview_id,
            "status": "completed",
            "duration_seconds": duration_seconds,
            "storage_path": storage_path,
        }
    except Exception as exc:
        logger.exception("Audio overview generation failed overview_id=%s notebook_id=%s", overview_id, notebook_id)
        try:
            repository.update_status(
                overview_id,
                "failed",
                {
                    "document_names": document_names,
                    "task_id": self.request.id,
                    "error_message": str(exc),
                },
            )
        except ValueError as update_exc:
            if _is_missing_overview_error(update_exc):
                _remove_uploaded_audio(client, settings.audio_overview_bucket, uploaded_storage_path)
                logger.info("Audio overview failure ignored because overview was deleted overview_id=%s", overview_id)
                return _cancelled_result(overview_id, "deleted")
            raise
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


def _require_min_duration(duration_seconds: float, minimum_seconds: int) -> None:
    if minimum_seconds <= 0:
        return

    if duration_seconds < minimum_seconds:
        raise ValueError(
            "Rendered audio duration "
            f"{duration_seconds:.1f}s is shorter than the required minimum of {minimum_seconds}s."
        )


def _is_missing_overview_error(exc: Exception) -> bool:
    return isinstance(exc, ValueError) and str(exc) == "Audio overview not found."


def _cancelled_result(overview_id: str, reason: str) -> dict[str, Any]:
    return {
        "overview_id": overview_id,
        "status": "cancelled",
        "reason": reason,
    }


def _remove_uploaded_audio(client: Any, bucket: str, storage_path: str | None) -> None:
    if not storage_path:
        return

    try:
        client.storage.from_(bucket).remove([storage_path])
    except Exception:
        logger.info("Could not remove cancelled audio object path=%s.", storage_path, exc_info=True)


def _summarize_context(
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    batch_context_chars: int,
) -> str:
    """Summarize long notebook context in batches before final script generation."""
    summaries: list[str] = []
    for batch in _split_text(context, max(1, int(batch_context_chars))):
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
    audio_config: Any,
    context: str,
    document_names: list[str],
    previous_script: str | None,
) -> dict[str, Any]:
    """Generate a podcast/news transcript as structured JSON."""
    retry_instruction = ""
    if previous_script:
        retry_instruction = (
            f"\nThe previous transcript was too short for a {_duration_label(audio_config.min_duration_seconds)} audio. "
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
- The spoken transcript must be at least {audio_config.min_script_words} words so the rendered audio can reach at least {_duration_label(audio_config.min_duration_seconds)} at a natural pace.
- If the documents are sparse, fill time with careful framing, definitions, implications, recap, and transitions, but do not invent unsupported facts.
- Do not invent human speaker names, host names, or personas.
- Do not address, greet, or refer to a co-host by name or label inside the spoken text. Avoid phrases like "Đúng vậy, Minh", "Bạn nói đúng, Speaker A", or "as you said".
- For podcast_dialogue, use exactly these neutral line labels only: {_speaker_label_examples(audio_config.podcast_speakers)}.
- For news_briefing, use exactly this neutral line label only: {_speaker_label_examples(audio_config.briefing_speakers)}.
- Speaker labels are only performance directions for TTS; the words after the colon must not mention the label or speaker identity.
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
            temperature=audio_config.script_temperature,
            max_output_tokens=audio_config.script_max_output_tokens,
            response_mime_type="application/json",
        ),
    )
    payload = _parse_json_object(str(response.text or ""))
    script_text = str(payload.get("script_text") or "").strip()
    if not script_text:
        raise ValueError("Gemini did not return an audio script.")

    style = str(payload.get("style") or "podcast_dialogue")
    source_speakers = payload.get("speakers")
    podcast_speakers = _configured_labels(audio_config.podcast_speakers)
    briefing_speakers = _configured_labels(audio_config.briefing_speakers)
    speakers = podcast_speakers if style == "podcast_dialogue" else briefing_speakers
    script_text = _normalize_script_speaker_labels(
        script_text,
        style,
        source_speakers,
        podcast_speakers,
        briefing_speakers,
    )

    return {
        "style": style,
        "title": str(payload.get("title") or "Audio Overview"),
        "speakers": speakers,
        "script_text": script_text,
    }


def _speaker_label_examples(labels: list[str]) -> str:
    return " and ".join(f'"{label}: text"' for label in labels)


def _duration_label(seconds: int) -> str:
    if seconds <= 0:
        return "full-length"

    minutes, remaining_seconds = divmod(seconds, 60)
    parts: list[str] = []
    if minutes:
        minute_unit = "minute" if minutes == 1 else "minutes"
        parts.append(f"{minutes} {minute_unit}")
    if remaining_seconds:
        second_unit = "second" if remaining_seconds == 1 else "seconds"
        parts.append(f"{remaining_seconds} {second_unit}")
    return " ".join(parts)


def _configured_labels(labels: Any) -> list[str]:
    configured = [str(label).strip() for label in labels] if isinstance(labels, list) else []
    configured = [label for label in configured if label]
    if not configured:
        raise ValueError("Audio overview labels must contain at least one value.")
    return configured


def _normalize_script_speaker_labels(
    script_text: str,
    style: str,
    source_speakers: Any,
    podcast_speakers: list[str],
    briefing_speakers: list[str],
) -> str:
    """Use stable non-persona speaker labels for TTS and script display."""
    if style != "podcast_dialogue":
        return _replace_line_labels(script_text, briefing_speakers)

    labels = podcast_speakers
    source_labels = [str(speaker).strip() for speaker in source_speakers] if isinstance(source_speakers, list) else []
    source_labels = [speaker for speaker in source_labels if speaker]
    label_map = {
        source_label: labels[index]
        for index, source_label in enumerate(source_labels[: len(labels)])
    }
    next_label_index = 0
    normalized_lines: list[str] = []

    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^([^:\n]{1,40}):\s*(.+)$", line)
        if match:
            speaker = match.group(1).strip()
            text = _strip_speaker_vocatives(
                match.group(2).strip(),
                [*source_labels, *label_map.keys(), *labels, speaker],
            )
            label = label_map.get(speaker)
            if not label:
                label = labels[next_label_index % len(labels)]
                label_map[speaker] = label
                next_label_index += 1
            normalized_lines.append(f"{label}: {text}")
            continue

        label = labels[next_label_index % len(labels)]
        next_label_index += 1
        normalized_lines.append(f"{label}: {_strip_speaker_vocatives(line, [*source_labels, *labels])}")

    return "\n".join(normalized_lines) if normalized_lines else script_text


def _replace_line_labels(script_text: str, labels: list[str]) -> str:
    normalized_lines: list[str] = []
    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^([^:\n]{1,40}):\s*(.+)$", line)
        text = match.group(2).strip() if match else line
        normalized_lines.append(f"{labels[0]}: {_strip_speaker_vocatives(text, labels)}")

    return "\n".join(normalized_lines) if normalized_lines else script_text


def _strip_speaker_vocatives(text: str, speaker_names: list[str]) -> str:
    cleaned = text.strip()
    unique_names = [name for name in dict.fromkeys(speaker_names) if name]
    for name in unique_names:
        escaped_name = re.escape(name)
        cleaned = re.sub(rf"^\s*{escaped_name}\s*[,，:;-]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"([,，]\s*){escaped_name}(?=\s*[.!?…。,:;])", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"([.!?…。]\s*){escaped_name}\s*[,，:;-]\s*", r"\1", cleaned, flags=re.IGNORECASE)

    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _render_tts_to_wav(
    *,
    genai_client: genai.Client,
    tts_model: str,
    audio_config: Any,
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
        podcast_voices = _configured_labels(audio_config.podcast_voices)
        if len(podcast_voices) < 2:
            raise ValueError("Audio overview podcast voices must contain at least two values.")
        speech_config = types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker=speakers[0],
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=podcast_voices[0])
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker=speakers[1],
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=podcast_voices[1])
                        ),
                    ),
                ]
            )
        )
    else:
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=audio_config.briefing_voice)
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
    _write_wave(wav_path, audio_bytes, rate=audio_config.audio_rate)


def _coerce_audio_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)


def _write_wave(path: Path, pcm: bytes, rate: int, channels: int = 1, sample_width: int = 2) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(rate)
        wav.writeframes(pcm)


def _encode_m4a(wav_path: Path, m4a_path: Path, bitrate: str, timeout_seconds: int) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to encode Audio Overview files as M4A.")

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", bitrate, str(m4a_path)],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "ffmpeg returned no output.").strip()
        raise RuntimeError(f"ffmpeg failed to encode M4A: {details}")


def _probe_duration(audio_path: Path, timeout_seconds: int) -> float:
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
        timeout=timeout_seconds,
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
