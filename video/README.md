# Demo video

`onevisit-demo.mp4`: 1:46, 1920×1080, no audio, all text on screen. Built from `film.html` (the scenes and timeline), which drives `proto.html` (a copy of `design/onevisit-prototype.html` with local fonts) in iframes.

Re-render:

```bash
cd video && python3 -m http.server 8765 &
python3 rec.py                      # Playwright records rec/*.webm; timing.txt has the start offset and length
ffmpeg -ss <offset> -i rec/<file>.webm -t <length> -c:v libx264 -crf 20 -pix_fmt yuv420p -r 30 -movflags +faststart onevisit-demo.mp4
```

The product footage is the clickable prototype, labelled "Prototype · example conversation". Every number on screen comes from `data/context/README.md` (City open data).
