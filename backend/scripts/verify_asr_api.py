"""Server-side checks for cloud ASR (no local model)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path

# Ensure backend root on path when run as script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)


def main() -> int:
    from app.asr_service import (
        asr_api_configured,
        asr_available,
        asr_provider,
        _require_cloud_asr,
        transcribe_media,
    )
    from app.ytdlp_service import YtdlpError

    print("provider", asr_provider())
    print("api_configured", asr_api_configured())
    print("available", asr_available())

    # 1) Always prove no-key path (override; never touches local models)
    saved = os.environ.get("ASR_API_KEY")
    os.environ["ASR_API_KEY"] = ""
    os.environ["ASR_PROVIDER"] = "api"
    try:
        _require_cloud_asr()
        print("REQUIRE_UNEXPECTED_OK")
        return 1
    except YtdlpError as e:
        print("REQUIRE_ERR", e.status_code, e.message)
        if "未配置云端 ASR" not in e.message:
            print("BAD_MESSAGE")
            return 1
        print("NO_KEY_OK")
    finally:
        if saved is None:
            os.environ.pop("ASR_API_KEY", None)
        else:
            os.environ["ASR_API_KEY"] = saved

    if not asr_api_configured():
        print("SKIP_CLOUD_CALL no key in .env")
        return 0

    # 2) With key: create tiny silent wav and call API path
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "silence.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000)  # 1s silence
        try:
            result = transcribe_media(wav_path)
            print("TRANSCRIBE_OK", json.dumps(result, ensure_ascii=False)[:300])
            return 0
        except YtdlpError as e:
            # Empty/silence / auth / network may fail — still proves API path was used
            print("TRANSCRIBE_ERR", e.status_code, e.message)
            if e.status_code in (422, 503, 504) and "本地" not in e.message and "faster" not in e.message.lower():
                print("ASR_FLOW_REACHED_CLOUD")
                return 0
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
