"""Playwright wrapper that turns a page into a compact text observation and executes actions."""

import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page

# Tags every visible interactive element with data-ac-id and returns a description of each.
_SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href], button, input, select, textarea, [role=button], [role=link], [role=tab], [role=menuitem], [onclick], summary';
  const els = Array.from(document.querySelectorAll(sel));
  const out = [];
  let i = 0;
  const labelFor = (el) => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return l.innerText.trim().split('\n')[0];
    }
    const parent = el.closest('label');
    if (parent) return parent.innerText.trim().split('\n')[0];
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  };
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (el.type === 'hidden') continue;
    const id = String(i++);
    el.setAttribute('data-ac-id', id);
    const tag = el.tagName.toLowerCase();
    const text = tag === 'select' ? '' :
      (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    const item = {id, tag, text: text.replace(/\s+/g, ' ').slice(0, 80)};
    if (el.type) item.type = el.type;
    if (tag === 'a') item.href = el.getAttribute('href');
    if (['input', 'select', 'textarea'].includes(tag)) {
      item.label = labelFor(el).slice(0, 80);
      item.value = (el.value || '').slice(0, 60);
      if (el.required) item.required = true;
    }
    if (tag === 'select') item.options = Array.from(el.options).map(o => o.text).slice(0, 15);
    if (el.disabled) item.disabled = true;
    item.small = parseFloat(st.fontSize) < 11;
    out.push(item);
  }
  return out;
}
"""


# Visible content images, so a text-only agent knows photos exist (and which are broken or undescribed).
_IMAGES_JS = r"""
() => Array.from(document.images)
  .filter(img => {
    const r = img.getBoundingClientRect();
    return r.width >= 60 && r.height >= 60 && getComputedStyle(img).visibility !== 'hidden';
  })
  .slice(0, 20)
  .map(img => ({
    alt: (img.getAttribute('alt') || '').trim().slice(0, 100),
    broken: img.complete && img.naturalWidth === 0,
  }))
"""

# "Loading...", "Searching…", "Loading profile..." etc.
_LOADING_RE = re.compile(r"\b(loading|searching|fetching)\b[^\n]{0,30}(\.\.\.|…)", re.I)


def _fmt_element(e: dict) -> str:
    parts = [f"[{e['id']}] {e['tag']}"]
    if e.get("type") and e["tag"] == "input":
        parts[0] += f"[{e['type']}]"
    if e.get("text"):
        parts.append(f'"{e["text"]}"')
    if e.get("label"):
        parts.append(f'label="{e["label"]}"')
    if e.get("value"):
        parts.append(f'value="{e["value"]}"')
    if e.get("options"):
        parts.append(f"options={e['options']}")
    if e.get("href"):
        parts.append(f"href={e['href']}")
    for flag in ("required", "disabled", "small"):
        if e.get(flag):
            parts.append(flag if flag != "small" else "(tiny text)")
    return " ".join(parts)


class Browser:
    def __init__(self, context: BrowserContext, base_url: str, shots_dir: Path, blocked_labels: list[str] = ()):
        self.context = context
        self.base_url = base_url
        self.shots_dir = shots_dir
        # Safety rails for real apps: controls the agent may not use, and no leaving the site.
        self.blocked_labels = [b.lower() for b in blocked_labels]
        self.host = urlparse(base_url).hostname
        self.page: Page | None = None

    async def start(self):
        self.page = await self.context.new_page()
        await self.page.goto(self.base_url, wait_until="domcontentloaded")

    async def settle(self, timeout: float = 10.0, quiet: float = 1.0) -> tuple[float, bool]:
        """Wait until client-rendered content has arrived: no loading text and the page text
        unchanged for `quiet` seconds. Returns (seconds waited, settled?)."""
        page = self.page
        start = time.monotonic()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
        except Exception:  # noqa: BLE001
            pass
        last, stable_since = None, time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:  # noqa: BLE001 - mid-navigation
                text = None
            now = time.monotonic()
            if text != last:
                last, stable_since = text, now
            elif text is not None and not _LOADING_RE.search(text) and now - stable_since >= quiet:
                return now - start, True
            await page.wait_for_timeout(250)
        return time.monotonic() - start, False

    async def observe(self, max_text: int = 3500) -> str:
        page = self.page
        waited, settled = await self.settle()
        elements = await page.evaluate(_SNAPSHOT_JS)
        images = await page.evaluate(_IMAGES_JS)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        text = "\n".join(line for line in text.splitlines() if line.strip())[:max_text]
        # Report load time the way a person would perceive it (minus our quiet-period check).
        load_s = max(0.0, waited - 1.0)
        if not settled:
            load_note = f"LOAD: still loading or changing after {waited:.0f}s"
        elif load_s >= 3:
            load_note = f"LOAD: content took about {load_s:.0f}s to appear"
        else:
            load_note = "LOAD: fast"
        lines = [
            f"URL: {page.url}",
            f"TITLE: {await page.title()}",
            load_note,
            "--- VISIBLE TEXT ---",
            text,
            "--- IMAGES ---",
            *(
                f'[img] {"(broken image)" if i["broken"] else "photo"}'
                + (f' alt="{i["alt"]}"' if i["alt"] else " (no description)")
                for i in images
            ),
            *(["(no images)"] if not images else []),
            "--- INTERACTIVE ELEMENTS ---",
            *(_fmt_element(e) for e in elements),
        ]
        return "\n".join(lines)

    async def screenshot(self, name: str) -> str:
        path = self.shots_dir / f"{name}.png"
        await self.page.screenshot(path=str(path), full_page=True)
        return path.name

    async def act(self, action: dict) -> str:
        """Execute an action; return a short description of what happened (or raise)."""
        page = self.page
        kind = action.get("type")
        # Models sometimes echo the id as "[3]" or "#3".
        raw = action.get("target")
        target = "" if raw is None else str(raw).strip("[]# ")
        loc = page.locator(f'[data-ac-id="{target}"]')
        if kind in ("click", "type", "select") and (not target or await loc.count() == 0):
            raise ValueError(f"there is no element [{target}] on this page")
        if kind in ("click", "type", "select") and self.blocked_labels:
            label = (await loc.first.evaluate(
                "el => (el.innerText || el.getAttribute('aria-label') || el.value || '').trim()")).lower()
            if any(b in label for b in self.blocked_labels):
                raise ValueError(f"[{target}] is off-limits in this simulation; pretend it is unavailable")
        if kind == "navigate" and urlparse(urljoin(page.url, action.get("url", "/"))).hostname != self.host:
            raise ValueError("navigating to other sites is not allowed in this simulation")
        before = page.url

        if kind == "click":
            await loc.first.click(timeout=5000)
        elif kind == "type":
            await loc.first.fill(str(action.get("text", "")), timeout=5000)
            if action.get("submit"):
                await loc.first.press("Enter")
        elif kind == "select":
            await loc.first.select_option(label=str(action.get("text", "")), timeout=5000)
        elif kind == "navigate":
            await page.goto(urljoin(page.url, action.get("url", "/")), wait_until="domcontentloaded")
        elif kind == "back":
            await page.go_back(wait_until="domcontentloaded")
        elif kind == "scroll":
            await page.mouse.wheel(0, 800)
        else:
            return f"no-op action {kind!r}"

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(300)
        if urlparse(page.url).hostname != self.host:
            left = page.url
            await page.goto(before, wait_until="domcontentloaded")
            return f"that led off-site to {left}; you were sent back (off-site pages are out of scope)"
        return f"page changed to {page.url}" if page.url != before else "stayed on same page"
