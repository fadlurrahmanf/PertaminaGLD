# Manual builder input

`spec.example.json` is a deliberately incomplete preparation template, not test
evidence. Fill it with actual screenshots and verified numbers before authoring.
Do not change the source images to simulate a UI state.

- `screenshots`: keys `hub`, `setup`, `recording`, `recovering`, `replaying`,
  `complete`. Adding `ready` adds a ninth page before `recording`; adding
  `incomplete` adds a separate buffer-limit page before troubleshooting (10 total).
- Each entry accepts `annotations` or the capture tool's `boxes`. Every item is
  `{n,x,y,w,h,title,body}`, with original-image pixel coordinates from top-left.
  Use 1-4 boxes per image. Omitted title/body use the relevant numbered default.
- Relative image paths resolve against the spec file. `kind` is `actual` for
  directly captured real application screens. A read-only viewer of unchanged
  logs from real GLD testing uses `kind: "recorded_actual"`, never `actual`.
- `recorded_actual` requires an existing `recorded_source` (or `source_evidence`)
  file path, `archive_banner_visible: true`, and `archive_banner` containing
  `TAMPILAN ULANG LOG UJI GLD ASLI - bukan koneksi langsung`. The actual viewer
  screenshot must visibly show that banner. Its caption must contain:
  `Tampilan ulang status yang direkam saat uji GLD asli; tidak mengendalikan perangkat.`
  This caption is supplied by default when omitted. No synthetic values/states
  may be inserted into the archive viewer or presented as device proof.
- Set `privacy_checked: true` globally or per entry only after checking original
  screenshots for visible credentials/tokens. Vector overlays are not secure
  redaction: original image pixels remain embedded in the PDF.
- Optional `crop: {x,y,w,h}` clips an actual source viewport without editing the
  raster. All annotation rectangles must lie within that viewport.
- Optional `caption` must fit on one line. Each page title and annotation title
  may occupy at most two lines. Keep four-column instruction bodies concise.
- Optional `pages` lists 6-10 keys (or `{key,title?,subtitle?,image?}` objects).
  Default pages add overview and troubleshooting as explicitly labelled
  illustrations. A missing UI screenshot is an error, never a fake substitute.
- Optional `test_results` requires `kind: "actual"` and `verified: true`.
  Supported cover metrics: `total_rows`, `replayed_rows`, `missing_rows`,
  `outage_seconds`, `csv_match`. Populate only from actual capture validation.
  Optional `cases` holds up to two such case summaries, each also including
  `complete` and `reason`; the overview distinguishes a complete recovery and
  an incomplete retention-limit case. Omit test_results until evidence exists.
  The guide explicitly limits physical verification to Model 1; Model 2/3 are
  build-only for this test campaign.

Preparation-only validation (no output file or PDF canvas):

```text
python build_manual.py --spec spec.json --validate-only
```

The coordinator must successfully run the PDF skill artifact marker immediately
before the first authoring command, then run:

```text
python build_manual.py --spec spec.json --output D:/Github/PertaminaGLD/output/pdf/Manual-GLD-Dataset-Wireless.pdf
```

Use the bundled Python runtime with ReportLab/Pillow. The builder writes the one
final PDF and a `layout-report.json` in this preparation directory. Render the
PDF with bundled Poppler and inspect every page before delivery. The output is
not accepted on text extraction alone.
