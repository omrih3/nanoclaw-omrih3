#!/opt/whisper/bin/python
"""Local speech-to-text (faster-whisper) for agent containers.

Usage: whisper-transcribe <audio-or-video-file> [--lang he|en|auto] [--model NAME]
                          [--out FILE] [--timestamps]

Prints the transcript to stdout (and to --out). Runs on CPU, int8. Only one
transcription runs at a time per container host share: a file lock serialises
calls so concurrent agents do not thrash the CPU.
"""
import argparse
import fcntl
import os
import sys
import time

MODEL_DIR = os.environ.get("WHISPER_MODEL_DIR", "/opt/whisper-models")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--lang", default="auto", help="he, en, ... or auto (default)")
    ap.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "large-v3-turbo"))
    ap.add_argument("--out")
    ap.add_argument("--timestamps", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        print(f"error: not a file: {a.file}", file=sys.stderr)
        return 2

    from faster_whisper import WhisperModel

    lock = open("/tmp/whisper.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # wait for any running transcription

    t0 = time.time()
    model = WhisperModel(
        a.model,
        device="cpu",
        compute_type="int8",
        download_root=MODEL_DIR,
        cpu_threads=int(os.environ.get("WHISPER_THREADS", os.cpu_count() or 2)),
    )
    segments, info = model.transcribe(
        a.file,
        language=None if a.lang == "auto" else a.lang,
        vad_filter=True,
        beam_size=5,
    )
    lines = []
    for s in segments:
        lines.append(f"[{s.start:.1f}-{s.end:.1f}] {s.text.strip()}" if a.timestamps else s.text.strip())
    text = "\n".join(lines).strip()
    print(f"# language={info.language} (p={info.language_probability:.2f}) "
          f"audio={info.duration:.0f}s took={time.time()-t0:.0f}s model={a.model}", file=sys.stderr)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
