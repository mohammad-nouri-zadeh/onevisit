import time, pathlib
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir="rec", record_video_size={"width": 1920, "height": 1080})
    t_open = time.time()
    pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://localhost:8765/film.html", wait_until="load")
    pg.wait_for_function("document.fonts.status === 'loaded'")
    pg.wait_for_timeout(800)
    t_start = time.time()
    pg.evaluate("window.__start()")
    pg.wait_for_function("window.__done === true", timeout=200000, polling=500)
    t_end = time.time()
    path = pg.video.path()
    ctx.close(); b.close()
    pathlib.Path("timing.txt").write_text(f"{t_start - t_open:.2f} {t_end - t_start:.2f}\n{path}\n")
    print("errors:", errs, "| start offset", round(t_start - t_open, 2), "| length", round(t_end - t_start, 1), "|", path)
