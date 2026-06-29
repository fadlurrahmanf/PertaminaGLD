# Design Documents

Status: current source mirror, 2026-06-29.

Folder ini menyimpan baseline import, draft historis, dan dokumen current-state yang diturunkan dari source firmware/server di repo saat ini.

## Current Reading Order

1. `gld/final_design.md`
2. `ch/final_design.md`
3. `gld-ch/payload-contract.draft.md`
4. `ch-ch/final_design.md`
5. `ch-gw/final_design.md`
6. `gw/final_design.md`
7. `gw-server/final_design.md`
8. `server/final_design.md`

## Immutable Baselines

- `gld/design.md` adalah imported original GLD design baseline.
- `ch/design.md` adalah imported original CH design baseline.
- Kedua file itu tidak diedit langsung sesuai aturan repo.
- `gld/design.updated.draft.md` dan `ch/design.updated.draft.md` tetap draft historis, bukan current implementation reference.

## Current Implementation References

- GLD node: `gld/final_design.md`
- CH node: `ch/final_design.md`
- GLD-CH wire payload: `gld-ch/payload-contract.draft.md`
- CH-CH multi-hop: `ch-ch/final_design.md`
- CH-Gateway boundary: `ch-gw/final_design.md`
- Gateway firmware: `gw/final_design.md`
- Gateway-server MQTT boundary: `gw-server/final_design.md`
- Server/Node-RED: `server/final_design.md`

## Source Priority

Jika ada konflik antara dokumen historis dan source, source yang menang:

- `firmware/platformio.ini`
- `firmware/config/*.h`
- `firmware/shared/include/*.h`
- `firmware/shared/src/*.cpp`
- `firmware/gld/include/*.h`
- `firmware/gld/src/*.cpp`
- `firmware/ch/include/*.h`
- `firmware/ch/src/*.cpp`
- `firmware/gateway/include/*.h`
- `firmware/gateway/src/*.cpp`
- `server/nodered/*.js`
- `server/nodered/*.json`
- `server/nodered/*.py`
