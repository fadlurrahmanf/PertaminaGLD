"""Build the standalone Operator Hub mockup.

Reads the production Simple Hub (apps/operator-hub/public) WITHOUT modifying it
and writes one self-contained HTML file next to this folder:

    apps/operator-hub/mockups/operator-hub-full-mockup.html

The production index.html and CSS are inlined unchanged; js/hub.js is inlined
inside a restartable function with one line adapted (simulate mode source).
Additions: a browser-side mock backend (replaces fetch + EventSource for
/api/simple/*) and a reviewer panel. Works from file://, a web server, or a
sandboxed preview iframe (about:srcdoc). Re-run after changing the production UI:

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

    hub_js = read(PUBLIC / "js" / "hub.js")
    # The only mockup adaptation of hub.js: let the reviewer panel choose the
    # built-in ?simulate= mode without navigating (sandboxed previews block it).
    simulate_line = 'const simulationMode = new URLSearchParams(location.search).get("simulate");'
    if hub_js.count(simulate_line) != 1:
        raise SystemExit("hub.js simulationMode line changed; update build.py")
    hub_js = script_safe(hub_js.replace(
        simulate_line,
        'const simulationMode = window.__mockSimulate ?? new URLSearchParams(location.search).get("simulate");',
    ))
    # Wrapped in a function (instead of a module that runs once) so the panel
    # can restart the Hub in place for a new scenario: no reload, no URL needed.
    hub_wrapper = (
        "<script>/* js/hub.js (production logic; wrapped for in-place restart) */\n"
        f'window.__bootHub = function () {{\n"use strict";\n{hub_js}\n}};\n</script>'
    )
    html, js_count = re.subn(
        r'<script type="module" src="\./js/hub\.js[^"]*"></script>',
        lambda _m: hub_wrapper,
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
