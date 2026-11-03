"""Headless recorder for training-video chapters, desktop or mobile.

A chapter's recording script (training/<site>/<NN>_<slug>/<NN>_<slug>.record.py) drives the site
with Playwright, one `with r.step("n.m"):` block per `> DO n.m:` line that belongs to the device
being filmed. This module:

- logs in and forces the UI language through edu_browser.Session (see that module for devices,
  the native-pixel capture, locale forcing and readiness waits);
- records the page with the Chrome DevTools screencast, at native device pixels;
- draws what headless capture lacks: a mouse pointer and click ripple on desktop, a tap ripple on
  mobile; scrolls visibly with the wheel on desktop and a smooth glide on mobile;
- paces the video: after each step it holds for exactly that step's measured TTS audio (`hold`);
- writes steps.json and <slug>.timed.md into the device's output folder, the silent video into the
  git-ignored .cache/, and review material into the git-ignored .work/<device>/.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

sys.path.insert(0, str(Path(__file__).parent))
from edu_browser import Device, Session, is_analytics
from edu_chapter import DO_RE, for_device, parse
from edu_lang import Lang
from edu_site import Site, drawtext_font, ffmpeg, ffprobe

FPS = 30

POINTER_JS = r"""
(() => {
  const install = () => {
    if (document.getElementById('__edu_cursor')) return;
    const c = document.createElement('div');
    c.id = '__edu_cursor';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2 L4 20 L9 15 L12.5 22 L15.5 20.6 L12 13.8 L19 13.8 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {position:'fixed', left:'-40px', top:'-40px', zIndex:2147483647,
      pointerEvents:'none', transform:'translate(-3px,-2px)', transition:'none'});
    document.documentElement.appendChild(c);
    const pos = window.__edu_pos;
    if (pos) { c.style.left = pos[0] + 'px'; c.style.top = pos[1] + 'px'; }
    document.addEventListener('mousemove', e => {
      window.__edu_pos = [e.clientX, e.clientY];
      c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px';
    }, true);
    document.addEventListener('mousedown', e => window.__edu_ripple(e.clientX, e.clientY, 18), true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
"""

RIPPLE_JS = r"""
window.__edu_ripple = (x, y, r) => {
  const d = document.createElement('div');
  Object.assign(d.style, {position:'fixed', left:(x-r)+'px', top:(y-r)+'px', width:(2*r)+'px',
    height:(2*r)+'px', borderRadius:'50%', border:'3px solid rgba(0,110,220,0.9)',
    background:'rgba(0,110,220,0.18)', zIndex:2147483646, pointerEvents:'none',
    transition:'transform 500ms ease-out, opacity 500ms ease-out'});
  document.documentElement.appendChild(d);
  requestAnimationFrame(() => { d.style.transform = 'scale(1.8)'; d.style.opacity = '0'; });
  setTimeout(() => d.remove(), 560);
};
"""

TOUCH_JS = r"""
document.addEventListener('touchstart', e => {
  for (const t of e.changedTouches) window.__edu_ripple(t.clientX, t.clientY, 22);
}, {capture: true, passive: true});
"""

HIGHLIGHT_JS = r"""
(el) => {
  const b = el.getBoundingClientRect();
  const d = document.createElement('div');
  Object.assign(d.style, {position:'fixed', left:(b.left-6)+'px', top:(b.top-6)+'px',
    width:(b.width+12)+'px', height:(b.height+12)+'px', borderRadius:'12px',
    border:'3px solid rgba(0,110,220,0.9)', zIndex:2147483646, pointerEvents:'none',
    transition:'opacity 400ms ease-out'});
  document.documentElement.appendChild(d);
  setTimeout(() => { d.style.opacity = '0'; }, 1400);
  setTimeout(() => d.remove(), 1850);
}
"""


class Recorder:
    """Use as a context manager. See the module docstring and recording.md."""

    def __init__(self, chapter_md: Path, lang: Lang, device: str, site: Site, env: str | None = None,
                 hold: dict[str, float] | None = None, line_gap: float = 0.4, margin: float = 0.8,
                 allow_production: bool = False):
        self.site, self.lang = site, lang
        self.session = Session(site, lang, device, env, allow_production)
        self.dev = self.session.dev
        self.device = device
        self.chapter_md = Path(chapter_md)
        self.slug = self.chapter_md.stem
        all_steps = parse(self.chapter_md)
        if len({s.id for s in all_steps}) != len(all_steps):
            raise SystemExit('Duplicate DO ids in the chapter.')
        self.steps = for_device(all_steps, device)
        self.by_id = {s.id: s for s in self.steps}
        lang_dir = self.chapter_md.parent
        self.out = lang_dir / device
        self.cache = lang_dir / '.cache' / device
        self.work = lang_dir / '.work' / device
        self.hold = hold
        self.line_gap, self.margin = line_gap, margin
        self.t = self.session.t
        self.frames_dir = self.work / 'frames'
        self.shots_dir = self.work / 'shots'
        self.frames: list[tuple[float, str]] = []
        self.log: list[dict] = []
        self.done_ids: list[str] = []
        self.page: Page | None = None
        self.setup_page: Page | None = None
        vw, vh = self.dev.viewport['width'], self.dev.viewport['height']
        self._pos = (vw * 0.5, vh * 0.6)
        self._t0: float | None = None
        self._end_ts = 0.0

    @property
    def mobile(self) -> bool:
        return self.dev.mobile

    # ---------- lifecycle ----------

    def __enter__(self) -> Recorder:  # noqa: PYI034
        for d in (self.frames_dir, self.shots_dir):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True)
        for stale in ('FAILED.png', 'network.log', 'sync_check.json', *[p.name for p in self.work.glob('contact_*.png')]):
            (self.work / stale).unlink(missing_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session.__enter__()
        self.setup_page = self.session.setup_page
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.page is not None:
                self._stop_screencast()
                if exc_type is not None:
                    self._fail_artifacts(exc)
        finally:
            if self.page is not None:
                with suppress(Exception):
                    self._netlog.close()
            self.session.__exit__(exc_type, exc, tb)
        if exc_type is None:
            self._finish()
        return False

    def open(self, page: Page, path: str) -> None:
        """Navigate, re-logging in off camera if the session expired, and wait for real content."""
        self.session.open(page, path)

    def start(self, path: str | None = None, before_filming=None) -> Page:
        """Open the chapter's start page (default: site.yaml start_page) in the recording context, then
        start filming. Overlays in dismiss_off_camera are closed and `before_filming(page)` runs first,
        both off camera."""
        scripts = (RIPPLE_JS, TOUCH_JS if self.dev.mobile else POINTER_JS)
        self._rec_ctx = self.session.new_context(init_scripts=scripts)
        self.page = self._rec_ctx.new_page()
        self._netlog = open(self.work / 'network.log', 'w', encoding='utf-8')  # noqa: SIM115 - closed in __exit__
        self.page.on('response', self._on_response)
        self.page.on('request', self._on_request)
        self.open(self.page, path or self.site.get('start_page') or '/')
        self.session.dismiss_overlays(self.page)
        if before_filming is not None:
            before_filming(self.page)
        if not self.dev.mobile:
            self.page.mouse.move(*self._pos)
        self.page.wait_for_timeout(300)
        self._cdp = self._rec_ctx.new_cdp_session(self.page)
        self._cdp.on('Page.screencastFrame', self._on_frame)
        w, h = self.dev.video
        self._cdp.send('Page.startScreencast', {
            'format': 'jpeg', 'quality': 92, 'maxWidth': w, 'maxHeight': h, 'everyNthFrame': 1,
        })
        self.page.wait_for_timeout(600)
        if not self.frames:
            # A static page may not repaint; nudge it to force a first frame.
            self.page.evaluate('window.scrollBy(0, 1); window.scrollBy(0, -1)')
            if not self.dev.mobile:
                self.page.mouse.move(self._pos[0] + 1, self._pos[1])
            self.page.wait_for_timeout(400)
        return self.page

    def _on_frame(self, f: dict) -> None:
        ts = f['metadata']['timestamp']
        name = f'{len(self.frames):06d}.jpg'
        (self.frames_dir / name).write_bytes(base64.b64decode(f['data']))
        self.frames.append((ts, name))
        if self._t0 is None:
            self._t0 = ts
        with suppress(PlaywrightError):
            self._cdp.send('Page.screencastFrameAck', {'sessionId': f['sessionId']})

    def _on_request(self, req) -> None:
        # Writes are logged when sent too, so a request that never answers still shows up.
        if req.method != 'GET' and req.resource_type in ('xhr', 'fetch') and not is_analytics(req.url):
            self._netlog.write(f'{self.rel():7.2f}s SENT {req.method} {req.url}\n')
            self._netlog.flush()

    def _on_response(self, resp) -> None:
        # Every write the app makes while filming: method, status, URL, and failure bodies only.
        req = resp.request
        if req.method == 'GET' or req.resource_type not in ('xhr', 'fetch') or is_analytics(req.url):
            return
        body = ''
        if resp.status >= 400:
            with suppress(PlaywrightError):
                body = resp.text()[:500]
        self._netlog.write(f'{self.rel():7.2f}s {resp.status} {req.method} {req.url} {body}\n')
        self._netlog.flush()

    def _stop_screencast(self) -> None:
        with suppress(PlaywrightError):
            self.page.wait_for_timeout(300)
            self._cdp.send('Page.stopScreencast')
        self._end_ts = time.time()

    def rel(self, ts: float | None = None) -> float:
        return (ts if ts is not None else time.time()) - (self._t0 or time.time())

    # ---------- steps ----------

    def narration_seconds(self, step_id: str) -> float:
        s = self.by_id[step_id]
        if not s.narration:
            return 0.0
        if self.hold is not None:
            return self.hold[step_id]
        words = sum(len(x.split()) for x in s.narration)
        return words / (self.lang.wpm / 60.0) + self.line_gap * len(s.narration) + self.margin

    def has(self, step_id: str) -> bool:
        """Whether this device's video has the step; device-tagged steps exist in one video only."""
        return step_id in self.by_id

    @contextmanager
    def step(self, step_id: str, extra_wait: float = 0.0):
        """One DO step. The body performs the actions. When it ends, the result must be on screen:
        that moment is the narration cue. The recorder then waits for the narration."""
        if step_id not in self.by_id:
            raise SystemExit(f'Step {step_id} is not a {self.device} DO id in {self.chapter_md.name}. '
                             'Guard device-tagged steps with r.has(id).')
        expected = self.steps[len(self.done_ids)].id
        if step_id != expected:
            raise SystemExit(f'Step {step_id} is out of order: the {self.device} video expects DO {expected} next.')
        start = self.rel()
        print(f'[{self.device} {step_id}] {self.by_id[step_id].instruction[:90]}')
        yield self.page
        # A click that navigates is still loading when the body returns; the cue must be a settled
        # screen with real content (no skeletons or spinners), or the sync check compares two
        # different moments of a page load and the narration describes an empty page.
        self.session.wait_ready(self.page)
        self.page.wait_for_timeout(250)
        cue = self.rel()
        self.page.screenshot(path=str(self.shots_dir / f'{step_id}.png'))
        wait = self.narration_seconds(step_id) + extra_wait
        self.page.wait_for_timeout(max(wait, 0.6) * 1000)
        self.log.append({'id': step_id, 'start': round(start, 2), 'cue': round(cue, 2),
                         'end': round(self.rel(), 2), 'narration_s': round(wait, 2)})
        self.done_ids.append(step_id)

    # ---------- visible actions ----------

    def _box_center(self, loc: Locator) -> tuple[float, float]:
        box = loc.bounding_box()
        return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2

    def _glide_into_view(self, loc: Locator, band: tuple[float, float] = (0.15, 0.8)) -> None:
        """Mobile: bring `loc` into the middle band of the screen with a smooth, visible scroll.
        Headless mobile emulation ignores both the mouse wheel and synthesized touch swipes
        (Input.synthesizeScrollGesture moved nothing, 2026-10-04), but a smooth scrollIntoView
        glides the page, inner scroll panels included."""
        h = self.dev.viewport['height']
        box = loc.bounding_box()
        if box is None or (box['y'] >= h * band[0] and box['y'] + box['height'] <= h * band[1]):
            return
        loc.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
        last = None
        for _ in range(40):                       # until it stops moving, at most 4 s
            self.page.wait_for_timeout(100)
            y = (loc.bounding_box() or {}).get('y')
            if y is not None and last is not None and abs(y - last) < 0.5:
                break
            last = y

    def move_to(self, loc: Locator, dwell: float = 0.35) -> None:
        loc.wait_for(state='visible')
        if self.dev.mobile:
            self._glide_into_view(loc)
            self.page.wait_for_timeout(dwell * 1000)
            return
        loc.scroll_into_view_if_needed()
        x, y = self._box_center(loc)
        dist = ((x - self._pos[0]) ** 2 + (y - self._pos[1]) ** 2) ** 0.5
        self.page.mouse.move(x, y, steps=max(8, min(40, int(dist / 18))))
        self._pos = (x, y)
        self.page.wait_for_timeout(dwell * 1000)

    def highlight(self, loc: Locator, secs: float = 1.2) -> None:
        """Draw a brief ring around `loc`: how a touch screen 'points at' something."""
        self.move_to(loc, dwell=0.2)
        loc.evaluate(HIGHLIGHT_JS)
        self.page.wait_for_timeout(secs * 1000)

    def hover(self, loc: Locator, secs: float = 1.2) -> None:
        """Desktop: move the pointer onto `loc` and dwell. Mobile has no hover: a highlight ring."""
        if self.dev.mobile:
            self.highlight(loc, secs)
        else:
            self.move_to(loc, dwell=secs)

    def click(self, loc: Locator, settle: float = 0.6) -> None:
        """Desktop: a visible pointer click. Mobile: a tap, with its ripple."""
        self.move_to(loc)
        if self.dev.mobile:
            x, y = self._box_center(loc)
            self.page.touchscreen.tap(x, y)
        else:
            self.page.mouse.down()
            self.page.wait_for_timeout(90)
            self.page.mouse.up()
        self.page.wait_for_timeout(settle * 1000)

    def select(self, loc: Locator, value: str | None = None, label: str | None = None, secs: float = 0.8) -> None:
        """A native <select>. Its option list is drawn by the operating system, not the page, so it never
        appears in the screencast: point at the field, then set the option; the field shows the new value.
        Custom dropdowns (a listbox drawn in the page) are clicked open with r.click instead."""
        self.hover(loc, secs=0.5)
        loc.select_option(value=value) if value is not None else loc.select_option(label=label)
        self.page.wait_for_timeout(secs * 1000)

    def type_text(self, loc: Locator, text: str, clear: bool = True, delay_ms: int = 55) -> None:
        self.click(loc, settle=0.2)
        if clear:
            loc.press('Control+A')
            loc.press('Delete')
            self.page.wait_for_timeout(250)
        loc.press_sequentially(text, delay=delay_ms)
        self.page.wait_for_timeout(400)

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(400)

    def wait_text(self, text: str, timeout_s: float = 20, fail_texts: tuple[str, ...] = ()) -> None:
        """Wait for a success message. If one of `fail_texts` appears instead, stop with its text."""
        ok = self.page.get_by_text(text, exact=False).first
        target = ok
        bads = [self.page.get_by_text(t, exact=False).first for t in fail_texts]
        for b in bads:
            target = target.or_(b)
        target.wait_for(timeout=timeout_s * 1000)
        for b in bads:
            if not ok.is_visible() and b.is_visible():
                raise RuntimeError(f'The app showed an error instead of {text!r}: {b.inner_text()!r}')

    def pause(self, secs: float) -> None:
        self.page.wait_for_timeout(secs * 1000)

    def scroll_to(self, loc: Locator, smooth: bool = False, band: float = 0.3) -> None:
        """Scroll visibly until `loc` sits in the upper part of the view: the mouse wheel on desktop
        (works inside inner scroll panels too), a smooth glide on mobile."""
        loc.wait_for(state='attached')
        if self.dev.mobile:
            self._glide_into_view(loc, band=(max(band - 0.15, 0.0), band + 0.35))
            self.page.wait_for_timeout(300)
            return
        vw, vh = self.dev.viewport['width'], self.dev.viewport['height']
        step = 60 if smooth else 140
        self.page.mouse.move(vw * 0.55, vh * 0.6)
        self._pos = (vw * 0.55, vh * 0.6)
        for _ in range(80):
            box = loc.bounding_box()
            if box is None:
                break
            target = vh * band
            if abs(box['y'] - target) < step:
                break
            self.page.mouse.wheel(0, step if box['y'] > target else -step)
            self.page.wait_for_timeout(90 if smooth else 45)
        self.page.wait_for_timeout(400)

    # ---------- outputs ----------

    def _fail_artifacts(self, exc) -> None:
        print(f'FAILED after steps {self.done_ids[-3:]}: {exc}', file=sys.stderr)
        with suppress(PlaywrightError):
            self.page.screenshot(path=str(self.work / 'FAILED.png'))
            print(f'  screenshot: {self.work / "FAILED.png"}', file=sys.stderr)

    def _finish(self) -> None:
        missing = [s.id for s in self.steps if s.id not in self.done_ids]
        if missing:
            raise SystemExit(f'The {self.device} recording ended without these DO steps: {", ".join(missing)}')
        mp4 = self._assemble()
        write_timed_md(self.chapter_md, self.out / f'{self.slug}.{self.lang.code}.{self.device}.timed.md',
                       self.log, self.device)
        (self.out / 'steps.json').write_text(json.dumps(self.log, indent=2) + '\n', encoding='utf-8', newline='\n')
        contact_sheets(self.shots_dir, self.log, self.work, self.dev)
        self.verify_sync(mp4)
        self.silent_mp4 = mp4
        dur = probe_duration(mp4)
        est = sum(self.narration_seconds(s.id) for s in self.steps)
        print(f'OK {self.device} video={mp4} duration={dur:.1f}s paced_narration={est:.1f}s steps={len(self.log)}')

    def _assemble(self) -> Path:
        """A constant-rate video whose frame i shows exactly what the page showed at i/FPS seconds after
        the first frame: for every output tick, the latest captured frame at or before it. Do NOT feed
        per-frame durations to ffmpeg's concat demuxer instead: with thousands of sub-1/30 s frames it
        drifted the video by 18 s against the step clock."""
        t0 = self.frames[0][0]
        # End one second after the last step: cleanup runs while the page idles.
        end = min(self._end_ts, t0 + self.log[-1]['end'] + 1.0) if self.log else self._end_ts
        n_out = int((end - t0) * FPS) + 1
        mp4 = self.cache / 'silent.mp4'
        w, h = self.dev.video
        proc = subprocess.Popen([
            ffmpeg(), '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-',
            '-vf', (f'scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=decrease,'
                    f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:white'),
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-r', str(FPS),
            '-an', '-movflags', '+faststart', str(mp4.resolve()),
        ], stdin=subprocess.PIPE)
        k, cached_name, cached = 0, None, b''
        for i in range(n_out):
            t = t0 + i / FPS
            while k + 1 < len(self.frames) and self.frames[k + 1][0] <= t:
                k += 1
            name = self.frames[k][1]
            if name != cached_name:
                cached_name, cached = name, (self.frames_dir / name).read_bytes()
            proc.stdin.write(cached)
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit('ffmpeg failed while assembling the video.')
        return mp4

    def verify_sync(self, mp4: Path, threshold: float = 6.0) -> list[tuple[str, float]]:
        """Compare the video frame at each step's cue with the screenshot taken at that moment. A mean
        absolute difference over `threshold` (0-255 greyscale, small thumbnails) means the video is not
        showing what the step clock says, and the narration would land on the wrong screen."""
        size = '108:192' if self.dev.portrait else '192:108'

        def grey(args: list[str]) -> bytes:
            return subprocess.check_output([ffmpeg(), '-v', 'error', *args, '-vf',
                                            f'scale={size},format=gray', '-f', 'rawvideo', '-'])
        report = []
        for e in self.log:
            shot = grey(['-i', str(self.shots_dir / f'{e["id"]}.png')])
            frame = grey(['-ss', f'{e["cue"]:.3f}', '-i', str(mp4), '-frames:v', '1'])
            n = min(len(shot), len(frame))
            diff = sum(abs(a - b) for a, b in zip(shot[:n], frame[:n])) / max(n, 1)
            report.append((e['id'], round(diff, 2)))
        bad = [r for r in report if r[1] > threshold]
        (self.work / 'sync_check.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
        print(f'Sync check ({self.device}): worst step {max(report, key=lambda r: r[1])}, {len(bad)} over {threshold}')
        if bad:
            raise SystemExit(f'Video is out of sync with the step clock at: {bad}. See .work/{self.device}/sync_check.json.')
        return report


def probe_duration(p: Path) -> float:
    return float(subprocess.check_output(
        [ffprobe(), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)]
    ).decode().strip())


def write_timed_md(chapter_md: Path, dest: Path, log: list[dict], device: str) -> None:
    """The chapter as one device's video plays it: the other device's steps left out, and a
    [mm:ss.s] cue in front of each step's first narration line."""
    cues = {e['id']: e['cue'] for e in log}
    out, pending, skipping = [], None, False
    for raw in chapter_md.read_text(encoding='utf-8').splitlines():
        s = raw.strip()
        m = DO_RE.match(s)
        if m:
            skipping = m[3] is not None and m[3] != device
            pending = None if skipping else cues.get(f'{m[1]}.{m[2]}')
            if skipping:
                continue
        elif s.startswith('#'):
            skipping = False
        elif skipping:
            continue
        elif s and not s.startswith('>') and pending is not None:
            mm, ss = divmod(pending, 60)
            raw = f'[{int(mm):02d}:{ss:04.1f}] {raw}'
            pending = None
        out.append(raw)
    dest.write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


def contact_sheets(shots_dir: Path, log: list[dict], work: Path, dev: Device) -> None:
    """One labelled screenshot per DO, twelve to a sheet, into work/contact_NN.png. The label sits at the
    bottom left: the top corners are where toasts appear (top left in right-to-left layouts)."""
    for stale in work.glob('contact_*.png'):
        stale.unlink()
    tw, th = dev.tile
    font = drawtext_font()
    shots = [shots_dir / f'{e["id"]}.png' for e in log]
    for i in range(0, len(shots), 12):
        group = shots[i:i + 12]
        args = [ffmpeg(), '-v', 'error', '-y']
        for s in group:
            args += ['-i', str(s)]
        labels = ''.join(
            f'[{k}]scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:white,'
            f'drawtext=fontfile=\'{font}\':text=\'DO {log[i + k]["id"]}\':x=8:y=h-th-8:fontsize=24:'
            f'fontcolor=yellow:box=1:boxcolor=black[v{k}];' for k in range(len(group))
        )
        layout = '|'.join(f'{(k % dev.cols) * tw}_{(k // dev.cols) * th}' for k in range(len(group)))
        inputs = ''.join(f'[v{k}]' for k in range(len(group)))
        filt = labels + (f'{inputs}xstack=inputs={len(group)}:layout={layout}:fill=white'
                         if len(group) > 1 else f'{inputs}null')
        subprocess.run(args + ['-filter_complex', filt, '-frames:v', '1',
                               str(work / f'contact_{i // 12 + 1:02d}.png')], check=True)
