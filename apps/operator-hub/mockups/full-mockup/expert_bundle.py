"""Bundle one Expert Console operator app into a single self-contained HTML string.

Used by build.py. Reads apps/<app>/ (index.html, CSS, ES modules) WITHOUT
modifying them. Every ES module is kept as its own module (so module-level
state and import/export semantics stay identical) but is delivered as a data:
URL behind an import map with bare specifiers. Relative specifiers cannot be
resolved from about:srcdoc, so they are rewritten to "@<app>/<path>". This
works from file://, a web server, and sandboxed preview iframes.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

SPECIFIER = re.compile(r"""(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(["'])(\.{1,2}/[^"']+)\2""")
CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?["']([^"']+)["']\)?\s*;""")


def _strip_query(path: str) -> str:
    return path.split("?", 1)[0]


def inline_css(path: Path, seen: set[Path] | None = None) -> str:
    seen = seen if seen is not None else set()
    path = path.resolve()
    if path in seen:
        return ""
    seen.add(path)
    text = path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        target = path.parent / _strip_query(match.group(1))
        return f"/* {target.name} */\n{inline_css(target, seen)}"

    return CSS_IMPORT.sub(replace, text)


def collect_modules(app_dir: Path, entry: Path, patches: dict[str, list[tuple[str, str]]]) -> dict[str, str]:
    """Return {bare specifier: rewritten source} for the entry and all its imports."""
    modules: dict[str, str] = {}
    pending = [entry.resolve()]
    while pending:
        file = pending.pop()
        spec = f"@{app_dir.name}/{file.relative_to(app_dir.resolve()).as_posix()}"
        if spec in modules:
            continue
        source = file.read_text(encoding="utf-8")
        for old, new in patches.get(file.name, []):
            if source.count(old) != 1:
                raise SystemExit(f"{app_dir.name}/{file.name}: patch anchor not found exactly once: {old[:70]!r}")
            source = source.replace(old, new)

        def rewrite(match: re.Match[str]) -> str:
            target = (file.parent / _strip_query(match.group(3))).resolve()
            if not target.is_file():
                raise SystemExit(f"{file}: import not found: {match.group(3)}")
            pending.append(target)
            bare = f"@{app_dir.name}/{target.relative_to(app_dir.resolve()).as_posix()}"
            return f"{match.group(1)}{match.group(2)}{bare}{match.group(2)}"

        modules[spec] = SPECIFIER.sub(rewrite, source)
    return modules


def bundle_app(
    app_dir: Path,
    *,
    title: str,
    head_scripts: list[str],
    patches: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    html = (app_dir / "index.html").read_text(encoding="utf-8")

    def link(match: re.Match[str]) -> str:
        href = _strip_query(match.group(1))
        return f"<style>/* {href} */\n{inline_css(app_dir / href)}</style>"

    html = re.sub(r"""<link rel="stylesheet" href="([^"]+)"\s*/?>""", link, html)
    entry_match = re.search(r"""<script type="module" src="([^"]+)"></script>""", html)
    if not entry_match:
        raise SystemExit(f"{app_dir.name}: module entry script not found")
    entry = app_dir / _strip_query(entry_match.group(1))
    modules = collect_modules(app_dir, entry, patches or {})
    imports = {
        spec: "data:text/javascript;base64," + base64.b64encode(source.encode("utf-8")).decode("ascii")
        for spec, source in modules.items()
    }
    entry_spec = f"@{app_dir.name}/{entry.resolve().relative_to(app_dir.resolve()).as_posix()}"
    loader = (
        f'<script type="importmap">{json.dumps({"imports": imports})}</script>\n'
        f'<script type="module">import "{entry_spec}";</script>'
    )
    html = html.replace(entry_match.group(0), loader, 1)
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)
    injected = "".join(f"<script>\n{script}\n</script>\n" for script in head_scripts)
    # Mock scripts must run before anything else in the document.
    return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + injected, html, count=1)
