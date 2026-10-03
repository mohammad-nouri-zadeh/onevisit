"""Soundtrack for onevisit-final.mp4: a calm music bed plus sound effects synced to the film.

All times are in the final video (cold open 0-8.1 s, then film2.html time + 8.1).
Usage: python3 sound.py out.wav
"""
import sys, wave
import numpy as np
from scipy.signal import butter, sosfilt

SR, DUR = 48000, 121.6
N = int(SR * DUR)
rng = np.random.default_rng(7)
music = np.zeros((N, 2)); sfx = np.zeros((N, 2))
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
def lp(x, f): return sosfilt(butter(2, f, "low", fs=SR, output="sos"), x, axis=0)
def hp(x, f): return sosfilt(butter(2, f, "high", fs=SR, output="sos"), x, axis=0)
def bp(x, lo, hi): return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x, axis=0)
def add(bus, t, sig, pan=0.0):
    i = int(t * SR)
    if i >= N or i + len(sig) <= 0: return
    sig = sig[: N - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    bus[i:i + len(sig), 0] += sig * l * 1.414; bus[i:i + len(sig), 1] += sig * r * 1.414
def env(n, a, d):  # attack/decay in samples, linear-exponential
    t = np.arange(n); e = np.minimum(1, t / max(a, 1)) * np.exp(-np.maximum(0, t - a) / max(d, 1)); return e
tt = lambda d: np.arange(int(d * SR)) / SR

# ---------- music ----------
BAR = 2.5                       # 96 bpm, 4/4
BEAT = BAR / 4
T0 = 8.1                        # grid starts at the title
CHORDS = [  # (bass, pad notes)
    (45, [57, 60, 64, 71]),     # Am9
    (41, [53, 57, 60, 64]),     # Fmaj7
    (48, [55, 60, 64, 62 + 12]),# Cadd9
    (43, [55, 59, 62, 64]),     # G6
]
def chord_at(t):
    k = int(max(0, t - T0) // (2 * BAR)) % 4
    return CHORDS[k] if t >= T0 else CHORDS[0]

# pad: additive, slow crossfaded chords, stereo detune
def pad_note(f, d, det):
    x = tt(d)
    s = np.sin(2 * np.pi * f * (1 + det) * x) + .35 * np.sin(2 * np.pi * 2 * f * x) + .12 * np.sin(2 * np.pi * 3 * f * (1 - det) * x)
    a = int(1.4 * SR); r = int(1.6 * SR); e = np.ones(len(x)); e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r)
    return s * e
seg = 2 * BAR
starts = [0.0] + [T0 + i * seg for i in range(int((DUR - T0) / seg) + 1)]
for i, st in enumerate(starts):
    d = (T0 if i == 0 else seg) + 1.6
    bass, notes = chord_at(st + 0.01)
    for j, m in enumerate(notes):
        add(music, st, .045 * pad_note(hz(m), d, .0015), pan=-.5 + j / 3)
    add(music, st, .07 * pad_note(hz(bass), d, 0), 0) if st >= 10.7 else None

# slow swell of the whole pad over the cold open
fade = np.ones(N); k = int(8.1 * SR); fade[:k] = np.linspace(.15, 1, k) ** 1.5
music *= fade[:, None]

# section intensity: plucks (arp), kick, hats
def pluck(f, d=.5, tau=.16):
    x = tt(d); return (np.sin(2 * np.pi * f * x) + .45 * np.sin(2 * np.pi * 2 * f * x) * np.exp(-x / .05)) * np.exp(-x / tau)
def kick():
    x = tt(.35); f = 45 + 75 * np.exp(-x / .04); return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x / .11)
KICK = kick()
HAT = hp(rng.standard_normal(int(.05 * SR)), 7000) * np.exp(-tt(.05) / .012)
step = BEAT / 2
t = T0
n = 0
while t < DUR - 2.5:
    bass, notes = chord_at(t)
    arp = [m + 12 for m in notes]
    seq = [0, 2, 1, 3, 2, 1, 3, 2]
    in_problem = 10.7 <= t < 37.6
    in_demo = 37.6 <= t < 106.2
    in_close = t >= 106.2
    beat_pos = n % 8
    if t >= 10.7 and t < 118.5:
        if in_demo or (in_problem and beat_pos % 2 == 0) or (in_close and beat_pos % 2 == 0):
            vol = .05 if in_demo else .04
            add(music, t, vol * pluck(hz(arp[seq[beat_pos]])), pan=.35 if beat_pos % 2 else -.35)
    if 37.6 <= t < 106.2:
        if beat_pos in (0, 4): add(music, t, .16 * KICK)
        if beat_pos % 2 == 1: add(music, t, .018 * HAT, pan=.3)
    if 19.5 <= t < 37.6 and beat_pos == 0:
        add(music, t, .09 * KICK)
    t += step; n += 1

# ending: hold the Am chord and fade to silence
for j, m in enumerate([45, 57, 60, 64, 71]):
    add(music, 116.3, (.05 if j else .07) * pad_note(hz(m), DUR - 116.3, .0015), pan=-.4 + j / 5)
k0 = int(119.6 * SR); music[k0:] *= np.linspace(1, 0, N - k0)[:, None]
music = lp(music, 9000)

# ---------- sound effects ----------
def whoosh(d=.6, lo=300, hi=3000):
    x = tt(d); s = bp(rng.standard_normal(len(x)), lo, hi); e = np.sin(np.pi * np.minimum(1, x / d)) ** 2; return s * e
def click():
    x = tt(.03); return (np.sin(2 * np.pi * 1800 * x) * np.exp(-x / .004) + .6 * hp(rng.standard_normal(len(x)), 2500) * np.exp(-x / .002))
def tick(f):
    x = tt(.02); return np.sin(2 * np.pi * f * x) * np.exp(-x / .003)
def pop(f, d=.18):
    x = tt(d); return np.sin(2 * np.pi * np.cumsum(f * (1 + .25 * np.exp(-x / .02))) / SR) * np.exp(-x / .06)
def chime(f, d=1.2):
    x = tt(d); return (np.sin(2 * np.pi * f * x) + .3 * np.sin(2 * np.pi * 2.01 * f * x) + .1 * np.sin(2 * np.pi * 3 * f * x)) * np.exp(-x / .35)
def swell(f0, f1, d):
    x = tt(d); f = f0 + (f1 - f0) * (x / d) ** .7; return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * x / d) ** 2
def thud():
    x = tt(.4); return np.sin(2 * np.pi * np.cumsum(60 + 40 * np.exp(-x / .03)) / SR) * np.exp(-x / .12)
def riser(d):
    x = tt(d); return bp(rng.standard_normal(len(x)), 400, 6000) * (x / d) ** 2.5
def impact():
    x = tt(1.6); return .9 * np.sin(2 * np.pi * np.cumsum(38 + 30 * np.exp(-x / .08)) / SR) * np.exp(-x / .5) + .25 * lp(rng.standard_normal(len(x)), 800) * np.exp(-x / .15)

# cold open: cuts between clips, riser into the title
for c in (2.7, 5.4): add(sfx, c - .25, .05 * whoosh(.5, 200, 1500))
add(sfx, 6.4, .06 * riser(1.7)); add(sfx, 8.1, .35 * impact())
# scene changes
for c in (10.7, 19.52, 31.73, 37.64, 79.13, 93.91, 106.24):
    add(sfx, c - .3, .07 * whoosh(.65), pan=rng.uniform(-.3, .3))
# 19,755 count-up: ticks slowing down like the counter
for k in range(28):
    p = k / 27; add(sfx, 11.0 + 2.2 * (1 - (1 - p) ** (1 / 3)) * .98, .05 * tick(1400 + 900 * p), pan=.2)
add(sfx, 13.25, .09 * chime(hz(81)))
# survey bars grow
add(sfx, 23.8, .06 * swell(220, 440, 1.6)); add(sfx, 29.5, .045 * swell(220, 330, 1.6))
# documents, then the missing one, then "book again"
for k, c in enumerate((31.73, 32.0, 32.25)): add(sfx, c + .1, .06 * pop(hz(76 + 2 * k)))
add(sfx, 32.6, .05 * pop(hz(70))); add(sfx, 33.5, .3 * thud()); add(sfx, 34.5, .09 * chime(hz(57)))
# language switch in the app
for c in (41.3, 42.1, 42.8, 43.5): add(sfx, c, .04 * pop(hz(84)), pan=.4)
# cursor clicks and button presses
for c in (45.6, 51.9, 68.8, 73.5, 91.3): add(sfx, c, .22 * click(), pan=.35)
for c in (52.3, 63.1, 69.6): add(sfx, c, .12 * click(), pan=.35)
# typing: the citizen's message and the comment after the appointment
for a, b in ((45.7, 47.2), (73.7, 75.0)):
    t = a
    while t < b:
        add(sfx, t, .03 * tick(rng.uniform(2200, 3400)), pan=.35); t += rng.uniform(.035, .075)
# Claude's reply, the options
add(sfx, 47.9, .06 * pop(hz(79))); add(sfx, 49.8, .05 * pop(hz(83)))
# checklist items appear
for k in range(6): add(sfx, 52.7 + .22 * k, .045 * pop(hz([72, 74, 76, 79, 81, 84][k])), pan=.35)
# source highlights
add(sfx, 54.9, .06 * chime(hz(88), .8)); add(sfx, 59.1, .05 * chime(hz(81), .8))
# "recorded as: page incomplete"
add(sfx, 75.4, .06 * chime(hz(84), .8))
# approval
add(sfx, 91.45, .08 * chime(hz(76))); add(sfx, 91.6, .06 * chime(hz(83)))
# Claude's five verbs light up, then "A person always decides"
for k, c in enumerate((97.7, 98.6, 99.2, 100.7, 102.0)): add(sfx, c, .06 * chime(hz([69, 72, 76, 79, 81][k]), .9), pan=-.4 + .2 * k)
add(sfx, 104.0, .25 * thud()); add(sfx, 104.0, .07 * chime(hz(57)))
# day one cards, then the closing line
for k, c in enumerate((110.6, 111.6, 112.8)): add(sfx, c, .07 * pop(hz([76, 79, 84][k])))
add(sfx, 116.3, .05 * whoosh(.8, 200, 1200)); add(sfx, 120.1, .06 * chime(hz(69), 1.4))

mix = music + sfx
mix = np.tanh(mix * 1.2) / 1.2
mix /= np.max(np.abs(mix)) / .89
pcm = (mix * 32767).astype("<i2")
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("wrote", sys.argv[1], f"{DUR}s")
