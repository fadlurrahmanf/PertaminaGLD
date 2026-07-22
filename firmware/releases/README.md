# Verified Firmware Release Packages

Release packages are created only from a clean Git checkout. The packager runs
a clean PlatformIO build itself, copies the resulting flash images, and writes a
schema-v2 manifest that binds the binaries to the source revision, PlatformIO
configuration, tool version, offsets, sizes, and SHA-256 digests.

Example from the repository root:

```powershell
python firmware/tools/package_firmware_release.py `
  --env gld `
  --device-id F011 `
  --board-profile WROOM-1U-N16R8
```

The command fails if the Git tree is dirty or the clean build fails. The GLD
operator must be given the complete generated package directory, not only its
`manifest.json`. It verifies every declared binary and flashes those packaged
bytes directly; it does not rebuild the current checkout.

Required schema-v2 identity fields include:

- firmware, protocol, and configuration-schema versions;
- clean 40-character Git commit;
- PlatformIO Core version and `platformio.ini` SHA-256;
- clean-build start/completion times;
- per-image path, flash offset, byte size, and SHA-256;
- a digest binding the complete ordered flash-file set.

The existing `F000_gld_v0.8.12_20260630T062122Z` folder is a legacy schema-v1
record. Its binaries are not tracked in this checkout and current operator
versions intentionally reject it for upload. Recreate any deployable release as
schema v2 from the exact reviewed source revision.

SHA-256 detects accidental or local package modification; it does not establish
publisher authenticity. If packages will be transferred through an untrusted
channel, add an organization-managed detached signature before deployment.
