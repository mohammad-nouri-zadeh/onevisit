"""Mix the AI voiceover (one wav per line) over sound.py's soundtrack, ducking the music under the voice.

Usage: python3 mix_voice.py VO_DIR soundtrack.wav out.wav
VO_DIR holds v0.wav ... v14.wav, one per line below. Each line starts at its time in the final video
(the film is timed to these) and is sped up slightly only if it would run into the next line.
"""
import subprocess, sys, wave
import numpy as np

VO, BED, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
STARTS = [11.2, 20.02, 32.13, 38.24, 41.18, 45.54, 52.74, 58.79, 63.75, 70.22, 79.73, 88.61, 94.71, 107.14, 116.75]
END = 121.0

def speech_span(path):
    with wave.open(path) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, ch).astype(float).mean(1) / 32768
    a = np.abs(x); thr = 0.01; idx = np.where(a > thr)[0]
    return max(0, idx[0] / sr - 0.04), min(len(x) / sr, idx[-1] / sr + 0.08)

ins, fl = [], []
for k, st in enumerate(STARTS):
    p = f"{VO}/v{k}.wav"; ins += ["-i", p]
    s, e = speech_span(p); d = e - s
    window = (STARTS[k + 1] if k + 1 < len(STARTS) else END) - st - 0.25
    tempo = min(1.3, max(1.0, d / window))
    ms = int(st * 1000)
    fl.append(f"[{k}:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,aresample=48000,atempo={tempo:.3f},"
              f"afade=in:d=0.02,adelay={ms}|{ms}[v{k}]")
    print(f"line {k:2d} at {st:6.2f}  {d:5.2f}s  window {window:5.2f}  tempo {tempo:.2f}")
n = len(STARTS)
fl.append("".join(f"[v{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,aformat=channel_layouts=stereo,"
          "loudnorm=I=-16:TP=-2:LRA=7,aresample=48000,asplit=2[vox][key]")
fl.append(f"[{n}:a]volume=0.55,aresample=48000[bed]")
fl.append("[bed][key]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=450:makeup=1[duck]")
fl.append("[vox][duck]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[out]")
subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-i", BED, "-filter_complex", ";".join(fl), "-map", "[out]",
                "-t", "121.6", "-c:a", "pcm_s16le", OUT], check=True)
print("wrote", OUT)
