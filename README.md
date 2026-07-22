# Pertamina GLD Repository

Root folder ini hanya berisi entry point utama. Detail pekerjaan disimpan di
folder yang sesuai supaya repo lebih mudah dibaca.

## Folder Utama

| Path | Isi |
|---|---|
| `ActivityAI/` | Activity log Codex/Claude dan rule AI-agent |
| `archive/` | File lama/unused yang disisihkan dengan konteks |
| `config/` | Contoh environment/config lokal |
| `docs/` | Desain, progress, resume, manual, dan chat checkpoint |
| `firmware/` | Firmware GLD, CH, Gateway, shared code, tests, PlatformIO |
| `logs/` | Log build, upload, deploy, dan verifikasi |
| `server/` | Node-RED flow dan script server/dataset |
| `skill/` | Skill lokal reusable untuk AI-agent |

## File Root

| File | Fungsi |
|---|---|
| `AGENTS.md` | Pointer ke `ActivityAI/rules/AGENTS.md` |
| `CLAUDE.md` | Pointer ke `ActivityAI/rules/CLAUDE.md` |
| `.gitignore` | Ignore rules untuk secret, build output, cache, dan logs |

## Config

Tidak ada `config.js` atau `config.md` di repo ini.

Config aktif/terkait ada di:

- `config/gld-unified.env.example`
- `config/gld-crypto.env.example`
- `firmware/config/LoraStarConfig.h`
- `firmware/config/LoraMeshConfig.h`
- `firmware/config/ServerConfig.h`
- `firmware/config/GldConfig.h`
- `firmware/config/ChConfig.h`
- `firmware/config/GwConfig.h`
- `firmware/shared/include/FirmwareConfig.h`
- `firmware/shared/src/FirmwareConfig.cpp`

## Build Final

Production/runtime firmware environments:

```text
gld
ch
gw
```

Field and power-cycle environments are intentionally separate from production:

```text
tfbg
gld_tpl5010_powercycle_test
chFieldtest
gw_hello_ack_fieldtest
```

The `*_fieldtest` and power-cycle images are non-production builds. They may
change timing or bypass battery shutdown behavior for controlled bench work and
must not be deployed as normal site firmware.

Build contoh:

```powershell
pio run -d firmware -e gld
```

Manual operasi GLD:

```text
docs/manual/gld-operation-manual.pdf
```
