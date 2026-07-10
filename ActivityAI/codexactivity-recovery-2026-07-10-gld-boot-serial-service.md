# Codex Recovery Note - 2026-07-10 13:39

Scope: keep GLD serial restart servicing alive during boot hardware probes.

Status log:

```text
[2026-07-10 13:39] PLANNED | Add serial/WDT service ticks and I2C timeout around GLD boot probe transactions after COM10 restart simulation showed boot could stall before loop | firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
[2026-07-10 13:39] DONE    | GLD boot I2C probes now set a 50 ms Wire timeout and service serial/WDT between transactions; host tests passed 34/34 | firmware/gld/src/GldUnifiedMain.cpp, firmware/tests/test_shared_protocol.py
```

Note: `ActivityAI/codexactivity.md` is currently corrupted with NUL bytes, so this recovery activity note is used instead of appending to that file.
