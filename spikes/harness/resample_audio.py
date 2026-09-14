#!/usr/bin/env python3
"""Resample harness/audio/*.wav (16 kHz) to harness/audio_24k/*.wav (24 kHz).

One-shot offline conversion for the Q2 24kHz probe (see README "Two-step Q2
probe"). Uses the FFmpeg on PATH (<home>\\tools\\ffmpeg); no network,
no dependency on make_audio.py's SAPI/PowerShell path -- this only resamples
existing files, it doesn't synthesize new ones, so folding it into
make_audio.py would just be an unrelated code path behind a flag.

Run: python resample_audio.py
"""
import shutil
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "audio"
DST_DIR = HERE / "audio_24k"
TARGET_RATE = 24000
FILES = ["rep_pitch.wav", "monitor_question.wav", "rep_then_question.wav"]
FFMPEG_TIMEOUT_S = 60  # generous for a few-second clip; never a hot loop
MAX_DURATION_DRIFT_S = 0.020  # 20ms


def wav_info(path: Path) -> tuple:
    with wave.open(str(path), "rb") as w:
        ch, sw, fr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    return ch, sw, fr, (nf / fr if fr else 0.0)


def resample(src: Path, dst: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ar", str(TARGET_RATE), "-ac", "1", "-c:a", "pcm_s16le",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    if r.returncode != 0:
        sys.exit(f"FATAL: ffmpeg failed on {src.name} (rc={r.returncode}):\n{r.stderr}")


def main():
    if shutil.which("ffmpeg") is None:
        sys.exit("FATAL: ffmpeg not found on PATH -- required for resample_audio.py")

    DST_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for name in FILES:
        src = SRC_DIR / name
        if not src.exists():
            print(f"SKIP: {src} not found (run make_audio.py first)")
            continue
        dst = DST_DIR / name
        resample(src, dst)

        txt = SRC_DIR / (Path(name).stem + ".txt")
        if txt.exists():
            shutil.copyfile(txt, DST_DIR / txt.name)

        s_ch, s_sw, s_fr, s_dur = wav_info(src)
        d_ch, d_sw, d_fr, d_dur = wav_info(dst)
        drift = abs(d_dur - s_dur)
        ok = (d_fr == TARGET_RATE and d_ch == 1 and d_sw == 2 and drift <= MAX_DURATION_DRIFT_S)
        rows.append((name, s_fr, s_ch, s_sw * 8, s_dur, d_fr, d_ch, d_sw * 8, d_dur, ok))
        if not ok:
            print(f"WARNING: {name} failed verification (rate={d_fr} ch={d_ch} "
                  f"bits={d_sw * 8} drift={drift * 1000:.1f}ms)")

    print()
    print(f"{'file':<22} {'src(rate/ch/bits/dur)':<26} {'out(rate/ch/bits/dur)':<26} ok")
    print("-" * 82)
    for name, s_fr, s_ch, s_bits, s_dur, d_fr, d_ch, d_bits, d_dur, ok in rows:
        print(f"{name:<22} {f'{s_fr}/{s_ch}/{s_bits}/{s_dur:.3f}s':<26} "
              f"{f'{d_fr}/{d_ch}/{d_bits}/{d_dur:.3f}s':<26} {ok}")

    if not rows or not all(r[-1] for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
