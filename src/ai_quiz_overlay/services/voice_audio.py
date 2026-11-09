"""In-memory microphone capture and local SenseVoice transcription."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
import re
import threading

from .voice_models import model_files


SAMPLE_RATE = 16_000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
FRAME_DURATION_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_DURATION_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE


class VoiceAudioError(RuntimeError):
    """A user-readable microphone or transcription error."""


class VoiceRecordingCancelled(VoiceAudioError):
    """The user cancelled capture and all audio should be discarded."""


@dataclass(frozen=True)
class VoiceCaptureResult:
    pcm: bytes
    duration_seconds: float
    speech_detected: bool
    stopped_by_silence: bool


@dataclass(frozen=True)
class MicrophoneDevice:
    name: str
    index: int
    host_api: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.host_api})" if self.host_api else self.name


def pcm_level(pcm: bytes) -> int:
    """Return a stable 0-100 level from mono int16 PCM."""
    if len(pcm) < 2:
        return 0
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    samples = array("h")
    samples.frombytes(usable)
    if not samples:
        return 0
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    rms = math.sqrt(mean_square)
    normalized = min(1.0, rms / 5000.0)
    return round(normalized * 100)


def list_microphone_devices() -> list[MicrophoneDevice]:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        host_apis = sd.query_hostapis()
    except Exception as exc:
        raise VoiceAudioError(friendly_audio_error(exc)) from exc

    result: list[MicrophoneDevice] = []
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        host_index = int(device.get("hostapi", -1))
        host_name = ""
        if 0 <= host_index < len(host_apis):
            host_name = str(host_apis[host_index].get("name", ""))
        result.append(
            MicrophoneDevice(
                name=str(device.get("name", f"输入设备 {index + 1}")),
                index=index,
                host_api=host_name,
            )
        )
    return result


def resolve_microphone_device(name: str) -> int | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    for device in list_microphone_devices():
        if device.name.strip().lower() == normalized:
            return device.index
    raise VoiceAudioError(
        f"找不到已保存的麦克风“{name}”，请在设置中重新选择。"
    )


def friendly_audio_error(exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if "permission" in lowered or "access" in lowered or "privacy" in lowered:
        return (
            "无法访问麦克风。请打开 Windows“设置 → 隐私和安全性 → "
            "麦克风”，允许桌面应用访问麦克风。"
        )
    if (
        "device unavailable" in lowered
        or "busy" in lowered
        or "unanticipated host error" in lowered
    ):
        return "麦克风可能正被其他程序占用，请关闭占用程序后重试。"
    if (
        "no default input device" in lowered
        or "invalid number of channels" in lowered
        or "error querying device" in lowered
    ):
        return "未检测到可用麦克风，请连接麦克风并检查 Windows 输入设备。"
    return f"麦克风启动失败：{text or type(exc).__name__}"


def record_once(
    *,
    device_name: str,
    silence_seconds: float,
    max_seconds: int,
    stop_event: threading.Event,
    cancel_event: threading.Event,
    level_callback=None,
    stream_factory=None,
    vad_factory=None,
) -> VoiceCaptureResult:
    """Capture mono 16-bit PCM in memory until stop, silence, or time cap."""
    if stream_factory is None or vad_factory is None:
        try:
            import sounddevice as sd
            import webrtcvad
        except Exception as exc:
            raise VoiceAudioError(friendly_audio_error(exc)) from exc
        if stream_factory is None:
            device_index = resolve_microphone_device(device_name)

            def stream_factory():
                return sd.RawInputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=FRAME_SAMPLES,
                    device=device_index,
                )

        if vad_factory is None:
            vad_factory = lambda: webrtcvad.Vad(2)

    vad = vad_factory()
    chunks = bytearray()
    frame_count = 0
    speech_detected = False
    silence_frames = 0
    silence_limit_frames = max(
        1,
        round(float(silence_seconds) * 1000 / FRAME_DURATION_MS),
    )
    max_frames = max(
        1,
        int(float(max_seconds) * 1000 / FRAME_DURATION_MS),
    )
    stopped_by_silence = False
    try:
        stream = stream_factory()
        with stream:
            while frame_count < max_frames:
                if cancel_event.is_set():
                    raise VoiceRecordingCancelled("录音已取消。")
                if stop_event.is_set():
                    break
                raw = stream.read(FRAME_SAMPLES)
                frame = bytes(raw)
                if not frame:
                    continue
                if len(frame) != FRAME_BYTES:
                    frame = frame[:FRAME_BYTES]
                    if len(frame) < FRAME_BYTES:
                        continue
                chunks.extend(frame)
                frame_count += 1
                if level_callback is not None:
                    level_callback(pcm_level(frame))
                try:
                    is_speech = bool(vad.is_speech(frame, SAMPLE_RATE))
                except Exception as exc:
                    raise VoiceAudioError(
                        f"静音检测失败：{exc}"
                    ) from exc
                if is_speech:
                    speech_detected = True
                    silence_frames = 0
                elif speech_detected:
                    silence_frames += 1
                    if silence_frames >= silence_limit_frames:
                        stopped_by_silence = True
                        break
        if cancel_event.is_set():
            raise VoiceRecordingCancelled("录音已取消。")
        return VoiceCaptureResult(
            pcm=bytes(chunks),
            duration_seconds=frame_count * FRAME_DURATION_MS / 1000,
            speech_detected=speech_detected,
            stopped_by_silence=stopped_by_silence,
        )
    except VoiceAudioError:
        raise
    except Exception as exc:
        raise VoiceAudioError(friendly_audio_error(exc)) from exc
    finally:
        chunks.clear()


_RECOGNIZERS: dict[str, object] = {}
_RECOGNIZER_LOCK = threading.Lock()
_SENSEVOICE_TAG = re.compile(r"<\|[^|>]*\|>")


def _load_recognizer(language: str):
    try:
        import sherpa_onnx
    except Exception as exc:
        raise VoiceAudioError(
            "语音识别组件未正确安装，请重新安装或重新打包程序。"
        ) from exc
    model_path, tokens_path = model_files()
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_path),
        tokens=str(tokens_path),
        num_threads=4,
        use_itn=True,
        language=language,
        debug=False,
    )


def transcribe_pcm(
    pcm: bytes,
    language: str,
    *,
    recognizer_loader=None,
) -> str:
    """Transcribe in-memory PCM without any network operation."""
    if not pcm:
        raise VoiceAudioError("没有录到可识别的声音。")
    loader = recognizer_loader or _load_recognizer
    with _RECOGNIZER_LOCK:
        recognizer = _RECOGNIZERS.get(language)
        if recognizer is None:
            recognizer = loader(language)
            _RECOGNIZERS[language] = recognizer
    samples = array("f")
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    integer_samples = array("h")
    integer_samples.frombytes(usable)
    samples.extend(sample / 32768.0 for sample in integer_samples)
    try:
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        text = str(stream.result.text).strip()
    except Exception as exc:
        raise VoiceAudioError(f"本地语音识别失败：{exc}") from exc
    finally:
        samples = array("f")
        integer_samples = array("h")
    text = _SENSEVOICE_TAG.sub("", text).strip()
    if not text:
        raise VoiceAudioError("没有识别出文字，请靠近麦克风后重试。")
    return text


def play_start_tone() -> None:
    """Play a short synthetic tone without shipping an audio asset."""

    def play() -> None:
        try:
            import winsound

            winsound.Beep(880, 70)
        except Exception:
            return

    threading.Thread(target=play, daemon=True).start()
