"""Build video/onevisit-final.mp4: B&W AI cold open + the recorded film retimed to the voiceover.

Inputs (not committed, regenerate with Higgsfield if needed):
  ASSETS/clips/c0.mp4 c1.mp4 c2.mp4   Higgsfield seedance_2_5 clips (prompts in video/README.md)
  ASSETS/vo/vo0.wav ... vo10.wav       Higgsfield seed_audio voiceover, one line of the script each
Usage: python3 build_final.py ASSETS
"""
import json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = pathlib.Path(sys.argv[1]).resolve()
WORK = ASSETS / "build"; WORK.mkdir(exist_ok=True)
SRC = HERE / "onevisit-demo.mp4"
FONT = HERE / "fonts" / "-F63fjptAgt5VM-kVkqdyU8n1i8q1w.woff2"   # IBM Plex Mono 400, latin
TEMPO = 1.06
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30"]

# voice segments: (file, start, end) in the original wav, trimmed to speech
SEG = {
    "P0": (0, 0.21, 8.60), "P1": (1, 0.52, 12.51), "P2": (2, 0.41, 5.83),
    "D3a1": (3, 0.36, 3.00), "D3a2": (3, 4.00, 7.27), "D3b": (3, 8.20, 15.30),
    "D4a": (4, 0.28, 6.32), "D4b": (4, 6.65, 10.85),
    "D5": (5, 0.29, 5.98), "D6": (6, 0.42, 9.45),
    "D7a": (7, 0.45, 8.27), "D7b": (7, 8.55, 12.66),
    "C8": (8, 0.30, 11.88), "Y9": (9, 0.44, 9.40), "Y10": (10, 0.33, 4.88),
}
def vdur(k): f, s, e = SEG[k]; return (e - s) / TEMPO

# chunks of the recorded film: (name, src_start, src_end, voices, lead, gap, tail, min_len)
CHUNKS = [
    ("title",  0.00,  6.50, [],               0,   0,    0,   2.6),
    ("f1",     6.50, 13.00, ["P0"],           0.5, 0,    0.4, 0),
    ("f2",    13.05, 21.45, ["P1"],           0.5, 0,    0.4, 0),
    ("f3",    21.45, 26.95, ["P2"],           0.4, 0,    0.4, 0),
    ("demoA", 26.95, 34.95, ["D3a1", "D3a2"], 0.6, 0.45, 0.3, 7.4),
    ("demoB", 34.95, 40.85, ["D3b"],          0.5, 0,    0.3, 0),
    ("chk1",  46.60, 50.10, ["D4a"],          0.2, 0,    0.2, 0),
    ("chk2",  50.10, 53.85, ["D4b"],          0.15, 0,   0.4, 0),
    ("office",53.85, 60.95, ["D5"],           0.6, 0,    0.5, 0),
    ("after", 60.95, 67.45, ["D6"],           0.6, 0,    0.4, 0),
    ("staffA",67.45, 72.50, ["D7a"],          0.6, 0,    0.3, 0),
    ("staffB",72.50, 80.80, ["D7b"],          1.2, 0,    0.6, 6.5),
    ("claude",80.80, 95.35, ["C8"],           0.8, 0,    0.6, 0),
    ("close", 95.35,106.40, ["Y9", "Y10"],    0.9, 0.7,  1.2, 0),
]
CLIPS = [("c0.mp4", 0.4, 2.7), ("c1.mp4", 0.6, 2.7), ("c2.mp4", 0.6, 2.7)]

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(" ".join(map(str, cmd))); print(r.stderr[-3000:]); sys.exit(1)

parts, placements, t = [], [], 0.0

# 1. cold open: B&W, label on every clip
label = (f"drawtext=fontfile='{FONT}':text='AI-generated scene':fontcolor=white@0.92:fontsize=24:"
         f"x=120:y=h-48-th-14:box=1:boxcolor=black@0.45:boxborderw=14")
for i, (f, ss, d) in enumerate(CLIPS):
    out = WORK / f"p{len(parts):02d}.mp4"
    vf = (f"scale=1920:1080:flags=lanczos,fps=30,hue=s=0,eq=contrast=1.10:brightness=-0.02,{label}")
    if i == 0: vf += ",fade=in:st=0:d=0.5"
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(ss), "-i", str(ASSETS / "clips" / f), "-t", str(d),
         "-vf", vf, "-an", *ENC, str(out)])
    parts.append(out); t += d

# 2. film chunks retimed to the voice
for name, s0, s1, voices, lead, gap, tail, min_len in CHUNKS:
    vt, starts = lead, []
    for j, k in enumerate(voices):
        if j: vt += gap
        starts.append(vt); vt += vdur(k)
    length = max(vt + tail if voices else 0, min_len)
    avail = s1 - s0
    vf = "fps=30"
    if length > avail: vf += f",tpad=stop_mode=clone:stop_duration={length - avail + 0.1:.3f}"
    if name == "close": vf += f",fade=out:st={length - 0.8:.3f}:d=0.8"
    out = WORK / f"p{len(parts):02d}.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{s0:.3f}", "-t", f"{min(avail, length):.3f}", "-i", str(SRC),
         "-vf", vf, "-t", f"{length:.3f}", "-an", *ENC, str(out)])
    for k, st in zip(voices, starts): placements.append((k, t + st))
    print(f"{name:7s} at {t:6.2f}  len {length:5.2f}  (src {avail:5.2f})  voices {[(k, round(t + s, 2)) for k, s in zip(voices, starts)]}")
    parts.append(out); t += length

# 3. concat video
lst = WORK / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
vid = WORK / "video.mp4"
run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(vid)])
total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vid)],
                             capture_output=True, text=True).stdout)

# 4. voice track
ins, fl = [], []
for i in range(11): ins += ["-i", str(ASSETS / "vo" / f"vo{i}.wav")]
for n, (k, at) in enumerate(placements):
    f, s, e = SEG[k]; ms = int(round(at * 1000))
    fl.append(f"[{f}:a]atrim={s}:{e},asetpts=PTS-STARTPTS,aresample=48000,atempo={TEMPO},"
              f"afade=in:d=0.03,afade=out:st={(e - s) / TEMPO - 0.06:.3f}:d=0.06,adelay={ms}|{ms}[a{n}]")
fl.append("".join(f"[a{n}]" for n in range(len(placements))) +
          f"amix=inputs={len(placements)}:normalize=0:duration=longest,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
aud = WORK / "voice.wav"
run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fl), "-map", "[aout]",
     "-c:a", "pcm_s16le", "-ar", "48000", str(aud)])

# 5. mux
final = HERE / "onevisit-final.mp4"
run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(aud), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
     "-af", "apad", "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(final)])
(WORK / "placements.json").write_text(json.dumps(placements, indent=1))
print(f"total {total:.2f}s -> {final}")
