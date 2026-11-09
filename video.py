import asyncio
import random
import shutil
import subprocess
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import MUSIC_VOLUME, TTS_RATE, TTS_VOICE, VOICE_MODE

W, H, FPS = 1080, 1920, 30
FIT = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
FONTS = ["assets/font.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]


def ensure_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    subprocess.run(["sudo", "apt-get", "update", "-qq"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)


def _run(cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {p.stderr[-1200:]}")
    return p.stdout


def duration(path):
    return float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=nw=1:nk=1", path]).strip())


def has_audio(path):
    return bool(_run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                      "stream=index", "-of", "csv=p=0", path]).strip())


# ---------- text graphics ----------
def _font(size):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_caption(img, text, size=62, y_center=0.22):
    """UGC-style white rounded boxes with black text."""
    draw = ImageDraw.Draw(img)
    font = _font(size)
    lines = _wrap(draw, text, font, W - 220)
    line_h = int(size * 1.35)
    y = int(H * y_center - line_h * len(lines) / 2)
    for line in lines:
        tw = draw.textlength(line, font=font)
        x = (W - tw) / 2
        draw.rounded_rectangle([x - 28, y - 8, x + tw + 28, y + line_h - 4], radius=18,
                               fill=(255, 255, 255, 240))
        draw.text((W / 2, y + line_h / 2 - 6), line, font=font, fill=(0, 0, 0, 255), anchor="mm")
        y += line_h
    return img


def _overlay_png(text, out):
    draw_caption(Image.new("RGBA", (W, H), (0, 0, 0, 0)), text).save(out)


def _tts(text, out):
    async def go():
        await edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE).save(str(out))
    asyncio.run(go())


def _prep_image(src, work, idx):
    out = work / f"img_{idx:02d}.jpg"
    ImageOps.exif_transpose(Image.open(src)).convert("RGB").save(out, quality=95)
    return out


# ---------- building ----------
def build_segment(src: Path, is_image: bool, shot: dict, idx: int, work: Path) -> Path:
    out = work / f"seg_{idx:02d}.mp4"
    target = max(float(shot.get("seconds") or 3), 1.5)
    vo_text = (shot.get("voiceover") or "").strip()
    if is_image:
        src = _prep_image(src, work, idx)

    if VOICE_MODE == "tts" and vo_text:
        vo = work / f"vo_{idx:02d}.mp3"
        _tts(vo_text, vo)
        dur, audio = duration(vo) + 0.35, ("file", vo)
    elif VOICE_MODE == "original" and not is_image and has_audio(src):
        dur, audio = min(duration(src), 15), ("clip", None)
    else:
        dur, audio = target, ("silent", None)

    inputs = ["-loop", "1", "-i", src] if is_image else ["-stream_loop", "-1", "-i", src]
    fc, n = [], 1
    base = f"[0:v]{FIT},fps={FPS}"
    text = (shot.get("on_screen_text") or "").strip()
    if text:
        ov = work / f"ov_{idx:02d}.png"
        _overlay_png(text, ov)
        inputs += ["-i", ov]
        fc.append(f"{base}[b];[b][{n}:v]overlay=0:0,format=yuv420p[v]")
        n += 1
    else:
        fc.append(f"{base},format=yuv420p[v]")

    if audio[0] == "file":
        inputs += ["-i", audio[1]]
        fc.append(f"[{n}:a]aresample=44100,apad[a]")
    elif audio[0] == "clip":
        fc.append("[0:a]aresample=44100[a]")
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        fc.append(f"[{n}:a]anull[a]")

    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
          "-t", f"{dur:.2f}", *ENC, out])
    return out


def _cover(src, is_image, hook, work):
    frame = work / "frame.jpg"
    if is_image:
        src = _prep_image(src, work, 99)
    seek = [] if is_image else ["-ss", "0.5"]
    _run(["ffmpeg", "-y", *seek, "-i", src, "-frames:v", "1", "-vf", FIT, "-q:v", "2", frame])
    img = draw_caption(Image.open(frame).convert("RGBA"), hook, size=84, y_center=0.40)
    cover = work / "cover.jpg"
    img.convert("RGB").save(cover, quality=92)
    return cover


def assemble(pairs, hook, work: Path):
    """pairs = [(shot_dict, local_path, is_image), ...] -> (final.mp4, cover.jpg)"""
    ensure_ffmpeg()
    segs = [build_segment(src, is_img, shot, i, work) for i, (shot, src, is_img) in enumerate(pairs)]
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segs))
    joined, final = work / "joined.mp4", work / "final.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    tracks = sorted(Path("assets/music").glob("*.mp3"))
    if tracks:
        mix = (f"[1:a]volume={MUSIC_VOLUME}[m];"
               "[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        _run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", random.choice(tracks),
              "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
              "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", final])
    else:
        _run(["ffmpeg", "-y", "-i", joined, "-c", "copy", "-movflags", "+faststart", final])

    if duration(final) < 3:
        raise RuntimeError("Reel is shorter than 3 seconds")
    first_shot, first_src, first_is_img = pairs[0]
    return final, _cover(first_src, first_is_img, hook, work)

