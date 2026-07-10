# Codex Recovery Note - 2026-07-10 13:32

Scope: echo GLD serial input characters so typed commands are visible in serial monitors without local echo.

Status log:

```text
[2026-07-10 13:32] PLANNED | Add GLD serial input echo on the same port where characters arrive, including visual backspace handling | firmware/gld/src/GldCommandParser.cpp, firmware/tests/test_shared_protocol.py
[2026-07-10 13:33] DONE    | GLD serial input now echoes typed characters to the same input port with newline and backspace handling; host tests passed 34/34 | firmware/gld/src/GldCommandParser.cpp, firmware/tests/test_shared_protocol.py
```

Note: `ActivityAI/codexactivity.md` is currently corrupted with NUL bytes, so this recovery activity note is used instead of appending to that file.
