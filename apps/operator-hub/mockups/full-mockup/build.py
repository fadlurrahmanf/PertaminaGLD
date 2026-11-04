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

import json
import re
from pathlib import Path

from expert_bundle import bundle_app

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent.parent / "public"
APPS = HERE.parents[2]
EXPERT = HERE / "expert"

# Expert Console apps reachable from the Hub's "Expert Console" button.
EXPERT_APPS = {
    "gld": ("gld-operator", "GLD Operator Mockup", "gld-device.js", {
        # Start the GLD Operator's own built-in simulator (normally ?mock=1).
        "main.js": [('new URLSearchParams(window.location.search).get("mock") === "1" && !state.mock',
                     '!state.mock /* mockup: built-in Mock mode always on */')],
    }),
    "ch": ("ch-operator", "CH Operator Mockup", "ch-device.js", {}),
    "gw": ("gw-operator", "Gateway Operator Mockup", "gw-device.js", {}),
}


def package_manifests(key: str) -> dict[str, object]:
    root = HERE.parents[1] / "firmware-packages"
    manifests: dict[str, object] = {}
    for manifest in sorted(root.glob(f"{key}*/latest/manifest.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("environment") == manifest.parent.parent.name:
            manifests[data["environment"]] = data
    return manifests


def build_expert(key: str) -> str:
    app, title, device_script, patches = EXPERT_APPS[key]
    scripts = [read(EXPERT / name) for name in ("storage-shim.js", device_script, "bridge-mock.js", "nav-shim.js")]
    # Real package manifests (metadata only, never the .bin files) so the
    # console's schema-v2 package validation runs exactly as in production.
    scripts.insert(1, f"window.__mockManifests = {json.dumps(package_manifests(key))};")
    return bundle_app(APPS / app, title=title, head_scripts=[script_safe(x) for x in scripts], patches=patches)
OUTPUT = HERE.parent / "operator-hub-full-mockup.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def script_safe(source: str) -> str:
    return re.sub(r"</(script)", r"<\\/\1", source, flags=re.IGNORECASE)


def json_in_script(value: str) -> str:
    # JSON allows "\\/", so this keeps "</script" from closing the data block.
    return json.dumps(value).replace("</", "<\\/")


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
    # Expert consoles are stored as JSON strings and opened in an iframe (srcdoc).
    expert_data = "".join(
        f'<script type="application/json" id="mockExpert-{key}">{json_in_script(build_expert(key))}</script>\n'
        for key in EXPERT_APPS
    )
    html = html.replace(
        "</body>",
        f"{expert_data}<script>/* mockup reviewer panel */\n{script_safe(read(HERE / 'mock-panel.js'))}</script>\n</body>",
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
