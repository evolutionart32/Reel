#!/usr/bin/env python3
"""Render an Evolution Group interior reel from raw footage.

Reproduces the house style measured from the brand's own reels:
vertical 1080x1920 @ 30fps, a centred Playfair Display title that fades in
and out over the opening seconds, the brand badge bottom-left, and a fade to
black on the tail.

Every geometric constant below was measured off the reference reels rather
than guessed; see SKILL.md for the numbers and how they were derived.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT = ASSETS / "PlayfairDisplay-Regular.ttf"
BADGE = ASSETS / "badge_evolution_group.png"

W, H, FPS = 1080, 1920, 30

# Title, measured on the reference: cap height 80px, ink width 634px for
# "BATHROOM", optical centre 540/966. Playfair Display Regular at 113px
# reproduces it to within antialiasing (per-glyph IoU 0.83).
TITLE_SIZE = 113
TITLE_TRACKING = 2.0
TITLE_CENTER_Y = 966

# Badge, measured on the reference: 277x77 at x=38, 42px off the bottom.
BADGE_W = 277
BADGE_X = 38
BADGE_BOTTOM = 42

# Timings, measured on the reference.
TITLE_IN = 0.35          # title starts fading in
TITLE_FADE_IN = 0.15
TITLE_OUT_END = 3.80     # title fully gone
TITLE_FADE_OUT = 0.35
END_FADE = 0.55          # fade to black on the tail


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd[:3])} ...\n{proc.stderr[-2500:]}")
    return proc


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-show_entries",
               "format=duration:stream=codec_type,width,height", "-of", "json", str(path)])
    return json.loads(out.stdout)


def duration_of(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def has_audio(path: Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def render_title(text: str, out_png: Path) -> None:
    """Draw the title on a full-frame transparent canvas, letter by letter.

    Per-letter placement is what lets us apply tracking; PIL has no
    letter-spacing of its own.
    """
    font = ImageFont.truetype(str(FONT), TITLE_SIZE)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    advances = [draw.textlength(ch, font=font) for ch in text]
    total = sum(advances) + TITLE_TRACKING * (len(text) - 1)

    # Draw once off-canvas to find the ink box, so we can centre on the ink
    # rather than on the font's metrics (which carry uneven side bearings).
    probe_img = Image.new("L", (int(total) + 400, TITLE_SIZE * 3), 0)
    probe_draw = ImageDraw.Draw(probe_img)
    x = 200.0
    for ch, adv in zip(text, advances):
        probe_draw.text((x, TITLE_SIZE), ch, font=font, fill=255)
        x += adv + TITLE_TRACKING
    bbox = probe_img.getbbox()
    if bbox is None:
        sys.exit("title rendered empty — check the text and the font file")
    ink_w, ink_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    origin_x = (W - ink_w) / 2 - (bbox[0] - 200.0)
    origin_y = TITLE_CENTER_Y - ink_h / 2 - (bbox[1] - TITLE_SIZE)

    x = origin_x
    for ch, adv in zip(text, advances):
        draw.text((x, origin_y), ch, font=font, fill=(255, 255, 255, 255))
        x += adv + TITLE_TRACKING
    img.save(out_png)


def normalize(src: Path, dst: Path, trim: tuple[float, float] | None) -> None:
    """Scale-and-crop one source to the 1080x1920 frame at a fixed rate.

    Segments have to share codec, rate and geometry or the lossless concat
    below will not join them.
    """
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if trim:
        cmd += ["-ss", f"{trim[0]:.3f}", "-t", f"{trim[1] - trim[0]:.3f}"]
    cmd += [
        "-i", str(src),
        "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:{H},fps={FPS},format=yuv420p"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(dst),
    ]
    if not has_audio(src):
        # Give silent sources a track anyway, so concat sees uniform streams.
        cmd[cmd.index("-i"):cmd.index("-i")] = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        cmd += ["-shortest"]
    run(cmd)


def concat(segments: list[Path], dst: Path, workdir: Path) -> None:
    if len(segments) == 1:
        shutil.copy(segments[0], dst)
        return
    listing = workdir / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in segments))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(dst)])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+", type=Path, help="raw clips, in order")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--title", help='title card text, e.g. "BATHROOM" (omit for no title)')
    ap.add_argument("--trim", action="append", default=[], metavar="START:END",
                    help="per-source trim in seconds; repeat once per source")
    ap.add_argument("--music", type=Path, help="music bed; replaces the source audio")
    ap.add_argument("--music-offset", type=float, default=0.0)
    ap.add_argument("--keep-source-audio", action="store_true",
                    help="keep camera audio instead of muting it under the music bed")
    ap.add_argument("--no-badge", action="store_true")
    ap.add_argument("--badge", type=Path, default=BADGE)
    ap.add_argument("--no-end-fade", action="store_true")
    ap.add_argument("--title-in", type=float, default=TITLE_IN)
    ap.add_argument("--title-out", type=float, default=TITLE_OUT_END)
    ap.add_argument("--draft", action="store_true", help="720p ultrafast, for checking cuts")
    args = ap.parse_args()

    for src in args.sources:
        if not src.exists():
            sys.exit(f"no such source: {src}")
    if args.trim and len(args.trim) != len(args.sources):
        sys.exit("--trim must be repeated once per source, in the same order")

    workdir = Path(tempfile.mkdtemp(prefix="reel_"))
    try:
        segments = []
        for i, src in enumerate(args.sources):
            trim = None
            if args.trim:
                start, end = args.trim[i].split(":")
                trim = (float(start), float(end))
            seg = workdir / f"seg_{i:02d}.mp4"
            normalize(src, seg, trim)
            segments.append(seg)

        base = workdir / "base.mp4"
        concat(segments, base, workdir)
        total = duration_of(base)

        inputs = ["-i", str(base)]
        filters = [f"[0:v]fps={FPS}[base]"]
        vlast = "base"
        idx = 1

        if args.title:
            title_png = workdir / "title.png"
            render_title(args.title, title_png)
            hold = max(0.0, args.title_out - args.title_in)
            if hold <= TITLE_FADE_OUT:
                sys.exit("title window is shorter than its fade-out")
            inputs += ["-loop", "1", "-t", f"{hold:.3f}", "-i", str(title_png)]
            # Rule: shift the overlay's own frame 0 to its window start, or the
            # overlay plays from its middle.
            filters.append(
                f"[{idx}:v]format=rgba,"
                f"fade=t=in:st=0:d={TITLE_FADE_IN}:alpha=1,"
                f"fade=t=out:st={hold - TITLE_FADE_OUT:.3f}:d={TITLE_FADE_OUT}:alpha=1,"
                f"setpts=PTS-STARTPTS+{args.title_in}/TB[title]"
            )
            filters.append(
                f"[{vlast}][title]overlay=0:0:"
                f"enable='between(t,{args.title_in},{args.title_out})'[vt]"
            )
            vlast, idx = "vt", idx + 1

        if not args.no_badge:
            if not args.badge.exists():
                sys.exit(f"no badge asset at {args.badge}")
            inputs += ["-i", str(args.badge)]
            filters.append(f"[{idx}:v]format=rgba,scale={BADGE_W}:-1[badge]")
            filters.append(
                f"[{vlast}][badge]overlay={BADGE_X}:H-h-{BADGE_BOTTOM}[vb]"
            )
            vlast, idx = "vb", idx + 1

        if not args.no_end_fade:
            filters.append(
                f"[{vlast}]fade=t=out:st={total - END_FADE:.3f}:d={END_FADE}[vout]"
            )
            vlast = "vout"

        # Audio. A music bed replaces camera audio unless asked otherwise; both
        # get loudness-normalised and fade with the picture.
        if args.music:
            if not args.music.exists():
                sys.exit(f"no such music file: {args.music}")
            inputs += ["-ss", f"{args.music_offset:.3f}", "-i", str(args.music)]
            music_idx = idx
            idx += 1
            bed = (f"[{music_idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                   f"afade=t=in:st=0:d=0.05")
            if args.keep_source_audio:
                filters.append(bed + "[bed]")
                filters.append(f"[0:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume=0.25[cam]")
                filters.append("[bed][cam]amix=inputs=2:duration=first:normalize=0[amix]")
                asrc = "amix"
            else:
                filters.append(bed + "[amix]")
                asrc = "amix"
        else:
            filters.append(f"[0:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS[amix]")
            asrc = "amix"

        tail = "" if args.no_end_fade else f",afade=t=out:st={total - END_FADE:.3f}:d={END_FADE}"
        filters.append(
            f"[{asrc}]loudnorm=I=-14:TP=-1:LRA=11{tail}[aout]"
        )

        vcodec = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
                  if args.draft else
                  ["-c:v", "libx264", "-preset", "slow", "-crf", "18"])

        args.output.parent.mkdir(parents=True, exist_ok=True)
        cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
               ["-filter_complex", ";".join(filters),
                "-map", f"[{vlast}]", "-map", "[aout]"] + vcodec +
               ["-pix_fmt", "yuv420p", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", str(args.output)])
        run(cmd)

        print(f"done: {args.output}  "
              f"{duration_of(args.output):.2f}s  "
              f"{args.output.stat().st_size / 1e6:.1f} MB")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
