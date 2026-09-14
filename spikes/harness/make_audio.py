#!/usr/bin/env python3
"""Generate offline test WAVs for ClauseCatcher API spikes.

$0, fully offline: uses Windows SAPI (System.Speech.Synthesis) via PowerShell,
which ships with Windows 11 -- no install, no network, no API key.

Format: 16-bit PCM, mono, 16000 Hz (matches AssemblyAI Streaming v3 default
exactly; see FORMAT.md for the Voice Agent API caveat). SAPI renders straight
into that format via SpeechAudioFormatInfo, so no resampling step is needed;
stdlib `wave` is used only to make silence and to concatenate clips.
"""
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO_DIR = HERE / "audio"
TMP_DIR = AUDIO_DIR / "_tmp"
SAMPLE_RATE = 16000
SAMPWIDTH = 2  # 16-bit
CHANNELS = 1
# SAPI synthesis of the longest clip (4-line REP_SCRIPT) plus PowerShell
# startup overhead; generous margin since this only runs a few times, never
# in a hot loop.
POWERSHELL_TIMEOUT_S = 120

REP_SCRIPT = [
    ("correct", "You can cancel with sixty days written notice before your renewal date each year."),
    ("contradiction", "Past fifty seats, we'll apply a ten percent volume discount automatically, no paperwork needed."),
    ("contradiction", "Our support team is available twenty four seven as part of the standard plan."),
    ("ambiguous", "We take data security seriously, you don't have to worry about anything after you leave us."),
]
MONITOR_QUESTION = "ClauseCatcher, what does clause four point two say about renewal?"

# ponytail: reading lines from a file (not passing them on the command line)
# sidesteps PowerShell quoting hell for text with apostrophes like "we'll".
TTS_PS1 = r"""
param(
    [string]$Voice,
    [string]$LinesFile,
    [string]$OutFile,
    [int]$SampleRate = 16000
)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) {
    try { $synth.SelectVoice($Voice) } catch { Write-Warning "Voice '$Voice' not found; using default." }
}
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    $SampleRate,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile($OutFile, $fmt)
Get-Content -Path $LinesFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line.Length -gt 0) { $synth.Speak($line) }
}
$synth.Dispose()
"""


def run_ps(args):
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"] + args
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=POWERSHELL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        sys.exit(
            f"FATAL: PowerShell timed out after {POWERSHELL_TIMEOUT_S}s "
            f"(hung SAPI/PowerShell process) running: {cmd}"
        )
    if r.returncode != 0:
        raise RuntimeError(f"PowerShell failed (rc={r.returncode}): {r.stderr}")
    return r.stdout


def list_voices():
    out = run_ps([
        "-Command",
        "Add-Type -AssemblyName System.Speech; "
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
        "| ForEach-Object { $_.VoiceInfo.Name }",
    ])
    return [v.strip() for v in out.splitlines() if v.strip()]


def tts_lines_to_wav(lines, voice, out_wav, ps1_path):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    lines_file = TMP_DIR / (out_wav.stem + "_lines.txt")
    lines_file.write_text("\n".join(lines), encoding="utf-8")
    run_ps([
        "-File", str(ps1_path),
        "-Voice", voice,
        "-LinesFile", str(lines_file),
        "-OutFile", str(out_wav),
        "-SampleRate", str(SAMPLE_RATE),
    ])


def make_silence(path, duration_s):
    nframes = int(duration_s * SAMPLE_RATE)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPWIDTH)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00" * (nframes * SAMPWIDTH))


def concat_wavs(out_path, in_paths):
    with wave.open(str(in_paths[0]), "rb") as w0:
        params = w0.getparams()
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for p in in_paths:
            with wave.open(str(p), "rb") as w:
                # bug fix: mismatched formats would silently concatenate raw
                # frames from different sample rates/widths into a WAV
                # declared at in_paths[0]'s format, corrupting playback.
                p_params = w.getparams()
                if (p_params.nchannels, p_params.sampwidth, p_params.framerate) != (
                    params.nchannels, params.sampwidth, params.framerate,
                ):
                    raise ValueError(
                        f"{p} format {p_params} does not match {in_paths[0]} format {params}"
                    )
                out.writeframes(w.readframes(w.getnframes()))


def describe_wav(path):
    with wave.open(str(path), "rb") as w:
        ch, sw, fr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        dur = nf / fr if fr else 0
    return f"{path.name}: channels={ch} sampwidth={sw} framerate={fr} duration={dur:.2f}s"


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    voices = list_voices()
    print("Installed SAPI voices:", voices)

    rep_voice = next((v for v in voices if "David" in v), voices[0] if voices else "")
    monitor_voice = next((v for v in voices if v != rep_voice), rep_voice)
    if rep_voice == monitor_voice:
        print("WARNING: only one usable voice found; rep and monitor will sound identical.")
    print(f"rep voice = {rep_voice!r}, monitor voice = {monitor_voice!r}")

    ps1_path = TMP_DIR / "tts.ps1"
    ps1_path.write_text(TTS_PS1, encoding="utf-8")

    # 1. rep_pitch.txt + rep_pitch.wav (4-line script, spoken as one clip)
    rep_txt = AUDIO_DIR / "rep_pitch.txt"
    rep_txt.write_text(
        "\n".join(f"{label}: {text}" for label, text in REP_SCRIPT) + "\n", encoding="utf-8"
    )
    rep_wav = AUDIO_DIR / "rep_pitch.wav"
    tts_lines_to_wav([text for _, text in REP_SCRIPT], rep_voice, rep_wav, ps1_path)

    # 2. monitor_question.txt + monitor_question.wav
    mon_txt = AUDIO_DIR / "monitor_question.txt"
    mon_txt.write_text(MONITOR_QUESTION + "\n", encoding="utf-8")
    mon_wav = AUDIO_DIR / "monitor_question.wav"
    tts_lines_to_wav([MONITOR_QUESTION], monitor_voice, mon_wav, ps1_path)

    # 3. rep_then_question.wav = rep line 1 + 2s silence + monitor question
    rep_line1_wav = TMP_DIR / "rep_line1.wav"
    tts_lines_to_wav([REP_SCRIPT[0][1]], rep_voice, rep_line1_wav, ps1_path)
    silence_wav = TMP_DIR / "silence_2s.wav"
    make_silence(silence_wav, 2.0)
    combo_wav = AUDIO_DIR / "rep_then_question.wav"
    concat_wavs(combo_wav, [rep_line1_wav, silence_wav, mon_wav])

    print()
    print("Generated files (format check via stdlib wave):")
    for f in [rep_wav, mon_wav, combo_wav]:
        print(" ", describe_wav(f))


if __name__ == "__main__":
    main()
