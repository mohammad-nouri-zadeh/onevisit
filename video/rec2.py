import sys, time, pathlib
from playwright.sync_api import sync_playwright
speed = sys.argv[1] if len(sys.argv) > 1 else "1"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir="rec2", record_video_size={"width": 1920, "height": 1080})
    t_open = time.time()
    pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.goto(f"http://localhost:8765/film2.html?speed={speed}", wait_until="load")
    pg.wait_for_function("document.fonts.status === 'loaded'")
    pg.wait_for_timeout(800)
    t_start = time.time()
    pg.evaluate("window.__start()")
    pg.wait_for_function("window.__done === true", timeout=200000, polling=200)
    t_end = time.time()
    path = pg.video.path()
    ctx.close(); b.close()
    pathlib.Path("timing2.txt").write_text(f"{t_start - t_open:.3f} {t_end - t_start:.3f}\n{path}\n")
    print("errors:", errs, "| start offset", round(t_start - t_open, 3), "| length", round(t_end - t_start, 2), "|", path)
