# Codex Recovery Note - 2026-07-10 13:27

Scope: add immediate GLD serial restart command.

Status log:

```text
[2026-07-10 13:27] PLANNED | Add GLD serial RESTART command that calls ESP.restart() | firmware/gld/include/GldCommandParser.h, firmware/gld/src/GldCommandParser.cpp, firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
[2026-07-10 13:29] DONE    | GLD serial RESTART command now ACKs and calls ESP.restart(); host tests passed 34/34 | firmware/gld/include/GldCommandParser.h, firmware/gld/src/GldCommandParser.cpp, firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
```

Note: `ActivityAI/codexactivity.md` is currently corrupted with NUL bytes, so this recovery activity note is used instead of appending to that file.
