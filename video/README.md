# Demo video

`onevisit-demo.mp4`: 1:46, 1920×1080, no audio, all text on screen. Built from `film.html` (the scenes and timeline), which drives `proto.html` (a copy of `design/onevisit-prototype.html` with local fonts) in iframes.

Re-render:

```bash
cd video && python3 -m http.server 8765 &
python3 rec.py                      # Playwright records rec/*.webm; timing.txt has the start offset and length
ffmpeg -ss <offset> -i rec/<file>.webm -t <length> -c:v libx264 -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart onevisit-demo.mp4
```

The product footage is the clickable prototype, labelled "Prototype · example conversation". Every number on screen comes from `data/context/README.md` (City open data).

## Final cut with voiceover

`onevisit-final.mp4`: 2:02, 1920×1080, 30 fps, H.264 + AAC. A 8 s black-and-white cold open (three Higgsfield `seedance_2_5` clips, labelled "AI-generated scene", invented people, no logos or signage), then the film above retimed to an English voiceover (Higgsfield `seed_audio`, preset voice "Ainsley", the team's script with numbers spelled out for pronunciation). Beats: problem 0:11–0:38, demo 0:38–1:34, where Claude works 1:34–1:46, day one 1:46–2:02.

Rebuild (the clips and voice files are not in the repo; put them in `ASSETS/clips/c0..c2.mp4` and `ASSETS/vo/vo0..vo10.wav`):

```bash
python3 video/build_final.py ASSETS
```

The script cuts `onevisit-demo.mp4` into scenes, holds the last frame where a voice line is longer than the scene, and mixes the voice at the computed times.
