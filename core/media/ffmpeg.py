"""ffmpeg helpers (optional: every function degrades with a clear message or a skip when ffmpeg is missing)."""
import re
import shutil
import subprocess
import wave
from pathlib import Path

FF = shutil.which("ffmpeg")
FP = shutil.which("ffprobe")


def have_ffmpeg() -> bool:
    return bool(FF and FP)


def _run(args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)


def duration(path: Path) -> float:
    path = Path(path)
    if path.suffix == ".wav":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def concat_wavs(files, out: Path, gap=0.35, lead=0.5):
    """Join mono 16-bit wavs (same rate) with silence between them. Pure python. Returns [(start, end)] per file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    spans, t = [], lead
    with wave.open(str(files[0])) as w0:
        sr = w0.getframerate()
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * lead))
        for i, f in enumerate(files):
            with wave.open(str(f)) as r:
                frames = r.readframes(r.getnframes())
                d = r.getnframes() / r.getframerate()
            w.writeframes(frames)
            spans.append((round(t, 3), round(t + d, 3)))
            t += d
            if i < len(files) - 1:
                w.writeframes(b"\x00\x00" * int(sr * gap))
                t += gap
    return spans


def tempo(src: Path, out: Path, factor: float):
    """Speed up/slow down speech without changing pitch (config audio.tempo). No-op copy at 1.0 or without ffmpeg."""
    if abs(factor - 1.0) < 1e-3 or not have_ffmpeg():
        shutil.copy(src, out)
        return
    _run(["-i", src, "-af", f"atempo={factor}", out])


def measure_lufs(path: Path):
    if not have_ffmpeg():
        return None
    err = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", err)
    return float(m[-1]) if m else None


def normalize(src: Path, out: Path, lufs: float, true_peak: float):
    if not have_ffmpeg():
        shutil.copy(src, out)
        return
    _run(["-i", src, "-af", f"loudnorm=I={lufs}:TP={true_peak}:LRA=11", "-ar", 48000, out])


def slideshow(images, durations, audio: Path | None, out: Path, size=(1280, 720), fit="pad"):
    """Still images + audio -> mp4 (preview/build). Real pipelines can swap in richer motion; this is the portable baseline.
    fit: "pad" letterboxes images of another shape, "crop" fills the frame and trims the edges."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not found: install ffmpeg (doctor shows the status)")
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".txt")
    rows = []
    for im, d in zip(images, durations):
        rows += [f"file '{Path(im).resolve().as_posix()}'", f"duration {d:.3f}"]
    rows.append(f"file '{Path(images[-1]).resolve().as_posix()}'")
    lst.write_text("\n".join(rows) + "\n", encoding="utf-8")
    args = ["-f", "concat", "-safe", 0, "-i", lst]
    if audio:
        args += ["-i", audio]
    w, h = size
    frame = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if fit == "crop" else
             f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
    args += ["-vf", f"{frame},fps=10,format=yuv420p",
             "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-crf", 30]
    if audio:
        args += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    _run(args + [out])
    lst.unlink(missing_ok=True)


def cut_vertical(src: Path, out: Path, start: float, seconds: float):
    """Centre-crop a 9:16 Short from a landscape video."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not found")
    _run(["-ss", f"{start:.2f}", "-i", src, "-t", f"{seconds:.2f}", "-vf", "crop=min(iw\\,ih*9/16):ih,scale=720:1280,format=yuv420p",
          "-c:v", "libx264", "-preset", "ultrafast", "-crf", 28, "-c:a", "aac", out])
