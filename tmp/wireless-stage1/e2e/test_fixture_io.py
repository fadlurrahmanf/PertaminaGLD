"""Bounded Windows evidence-publication race probe, private temporary files."""
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    target = Path(temporary) / "evidence.json"
    pending = Path(temporary) / "evidence.tmp"
    target.write_text('{"old": true}', encoding="utf-8")
    pending.write_text('{"new": true}', encoding="utf-8")
    with target.open("r", encoding="utf-8"):
        try:
            pending.replace(target)
            result = "replace while reader open: succeeds"
        except OSError as error:
            result = "replace while reader open: " + type(error).__name__
    print(result)
    if pending.exists():
        pending.replace(target)
        print("replace after reader closes: succeeds")
