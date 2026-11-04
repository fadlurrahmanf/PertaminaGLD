"""Build the standalone Operator Hub mockup.

Reads the production Simple Hub (apps/operator-hub/public) WITHOUT modifying it
and writes one self-contained HTML file next to this folder:

    apps/operator-hub/mockups/operator-hub-full-mockup.html

The production index.html, CSS, and js/hub.js are inlined unchanged. The only
additions are a browser-side mock backend (replaces fetch + EventSource for
/api/simple/*) and a reviewer panel. Re-run after changing the production UI:

    python apps/operator-hub/mockups/full-mockup/build.py
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent.parent / "public"
OUTPUT = HERE.parent / "operator-hub-full-mockup.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def script_safe(source: str) -> str:
    return re.sub(r"</(script)", r"<\\/\1", source, flags=re.IGNORECASE)


def build() -> str:
    html = read(PUBLIC / "index.html")

    def inline_css(match: re.Match[str]) -> str:
        href = match.group(1).split("?", 1)[0].removeprefix("./")
        return f"<style>/* {href} */\n{read(PUBLIC / href)}</style>"

    html, css_count = re.subn(r'<link rel="stylesheet" href="([^"]+)">', inline_css, html)
    if css_count != 3:
        raise SystemExit(f"expected 3 production stylesheets, found {css_count}")

    hub_js = script_safe(read(PUBLIC / "js" / "hub.js"))
    html, js_count = re.subn(
        r'<script type="module" src="\./js/hub\.js[^"]*"></script>',
        lambda _m: f'<script type="module">/* js/hub.js (production, unchanged) */\n{hub_js}</script>',
        html,
    )
    if js_count != 1:
        raise SystemExit("production hub.js script tag not found")

    html = html.replace(
        "<title>Pertamina GLD - Operator Hub</title>",
        "<title>Operator Hub Mockup</title>\n"
        '  <meta name="description" content="Mockup mandiri Operator Hub Pertamina GLD: UI produksi dengan backend simulasi di browser.">',
        1,
    )
    head_extra = (
        f"<style>/* mockup reviewer chrome */\n{read(HERE / 'mock-panel.css')}</style>\n"
        f"<script>/* mockup backend */\n{script_safe(read(HERE / 'mock-backend.js'))}</script>\n"
    )
    html = html.replace("</head>", head_extra + "</head>", 1)
    html = html.replace(
        "</body>",
        f"<script>/* mockup reviewer panel */\n{script_safe(read(HERE / 'mock-panel.js'))}</script>\n</body>",
        1,
    )
    banner = (
        "<!--\n  GENERATED FILE - do not edit by hand.\n"
        "  Source: apps/operator-hub/public (unchanged) + apps/operator-hub/mockups/full-mockup.\n"
        "  Rebuild: python apps/operator-hub/mockups/full-mockup/build.py\n-->\n"
    )
    return html.replace("<!doctype html>\n", "<!doctype html>\n" + banner, 1)


if __name__ == "__main__":
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(HERE.parents[3])} ({OUTPUT.stat().st_size} bytes)")
