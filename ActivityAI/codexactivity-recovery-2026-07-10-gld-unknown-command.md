# Codex Recovery Note - 2026-07-10 13:29

Scope: print an English unknown-command response for unsupported GLD serial commands.

Status log:

```text
[2026-07-10 13:29] PLANNED | Add GLD serial unknown-command feedback using the typed command text | firmware/gld/include/GldCommandParser.h, firmware/gld/src/GldCommandParser.cpp, firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
[2026-07-10 13:31] DONE    | Unknown GLD serial commands now print "<command> command is unknown" through raw serial output even when debug is off; host tests passed 34/34 | firmware/gld/include/GldCommandParser.h, firmware/gld/src/GldCommandParser.cpp, firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
```

Note: `ActivityAI/codexactivity.md` is currently corrupted with NUL bytes, so this recovery activity note is used instead of appending to that file.
