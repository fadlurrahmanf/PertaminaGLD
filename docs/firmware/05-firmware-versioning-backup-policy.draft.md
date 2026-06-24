# Firmware Versioning And Backup Policy Draft

**Status:** pre-coding policy  
**Scope:** firmware source versioning, build metadata, changelog, and rollback backup  
**Rule:** applies when firmware implementation starts after explicit user approval.

---

## 1. Version Format

Firmware uses:

```text
MAJOR.MINOR.PATCH
```

Initial official firmware versions:

```text
GLD = 0.1.0
CH  = 0.1.0
```

Move to `1.0.0` only after firmware is field-ready / production-ready.

---

## 2. Bump Rules

`PATCH`:

- bugfix,
- small refactor,
- log/comment/runtime text change,
- test fix that changes firmware source,
- small non-breaking behavior change,
- any official source/config change that does not qualify as minor or major.

`MINOR`:

- backward-compatible feature,
- new command that does not break old config/protocol,
- new Modbus register that does not change old register meaning,
- new dataset/nulling/health capability that remains compatible.

`MAJOR`:

- breaking wire protocol change,
- incompatible config schema change,
- changed meaning of `gasClass`,
- changed encrypted payload layout,
- rollback requires migration or manual conversion.

Every official firmware source/config change must bump at least `PATCH`.

---

## 3. Build Metadata

Each firmware exposes:

```text
FIRMWARE_NAME
FIRMWARE_VERSION
BUILD_DATE_TIME
GIT_COMMIT
PROTOCOL_VERSION
CONFIG_SCHEMA_VERSION
```

Build date format:

```text
YYYY-MM-DD HH:mm:ss Asia/Jakarta
```

Example:

```text
2026-06-16 10:42:15 Asia/Jakarta
```

Rules:

- Build date changes every build.
- Firmware version changes only when source/config changes enter an official build.
- Rebuilding the same source may keep the same firmware version while build date changes.
- Firmware version is separate from protocol version, model profile, and nulling profile.

---

## 4. Version History File

Use:

```text
firmware/versions/version.md
```

Style follows `D:\GasleakDetectorDesign\versions\version.md`:

```md
## v0.1.1 - 2026-06-16 10:42:15 Asia/Jakarta

**Summary:** Perbaiki payload builder GLD dan konstanta threshold phase 1.

### Changed Files
- firmware/shared/include/ProtocolConstants.h
- firmware/shared/src/GldPayload.cpp

### Rollback
Restore changed files from `firmware/versions/backups/v0.1.0/`.
```

For large versions, add `### Detailed Changes` grouped by subsystem.

---

## 5. Backup Flow

For each official update:

1. Determine the new version.
2. List firmware source/config files that will change.
3. Backup only those files before editing.
4. Store backups under the previous version folder:

```text
firmware/versions/backups/vX.Y.Z/
```

5. Preserve original relative paths inside the backup folder.
6. Edit/update files.
7. Update `firmware/versions/version.md`.
8. Build/test.
9. Mark version valid only after tests pass.

Example:

```text
firmware/versions/backups/v0.1.0/firmware/shared/include/ProtocolConstants.h
firmware/versions/backups/v0.1.0/firmware/shared/src/GldPayload.cpp
```

Meaning: those files are the pre-change copies from `v0.1.0` before producing `v0.1.1`.

---

## 6. Storage Optimization

Do:

- backup only changed files,
- keep relative paths,
- keep `version.md` concise,
- use git as the main history,
- use backups for fast manual rollback,
- keep full binary artifacts only for milestone versions.

Do not backup:

- `.pio/`,
- build output directories,
- cache directories,
- dependency folders,
- generated binaries for every patch,
- unchanged source files.

Recommended binary retention:

- keep binaries for `0.1.0`, `0.2.0`, `1.0.0`, and field-test releases,
- do not keep binaries for every tiny patch unless the patch was deployed.

---

## 7. Rollback Rule

Rollback a version by restoring only files listed in that version entry.

Example:

```text
Current: v0.1.1
Rollback target: v0.1.0
Backup source: firmware/versions/backups/v0.1.0/
```

Restore files from that backup folder to their original paths.

If a version changed 1 file, restore 1 file.  
If a version changed 2 files, restore 2 files.

---

## 8. Separation Rules

- Firmware version is not protocol version.
- Firmware version is not `modelProfileId`.
- Firmware version is not `nullingProfileId`.
- Firmware version is not `keyId`.
- Document-only changes do not require firmware version bump.
- Firmware source/config changes require firmware version bump before official build.

---

## 9. Implementation Notes

When coding starts, add:

- shared firmware version constants,
- GLD firmware version constants,
- CH firmware version constants,
- host test for `MAJOR.MINOR.PATCH` format,
- build metadata injection for date/time and git commit.

The first coding milestone should initialize:

```text
GLD 0.1.0
CH  0.1.0
PROTOCOL_VERSION 0.1.0
CONFIG_SCHEMA_VERSION 0.1.0
```
