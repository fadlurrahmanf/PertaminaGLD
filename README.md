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

Main firmware env final:

```text
gld_unified_esp32s3
ch_star_mesh_runtime_esp32s3
gateway_mqtt_mesh_esp32s3
```

Build contoh:

```powershell
pio run -d firmware -e gld_unified_esp32s3
```

Manual operasi GLD:

```text
docs/manual/gld-operation-manual.pdf
```
