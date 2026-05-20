# labelforge

Self-hosted web app for designing, saving, and printing labels to Brother QL series printers.

**Status**: Early development. Not yet usable.

## What it does

- Quick-print mode (text + font, like brother_ql_web)
- Save labels as named templates with variable fields
- Recall templates, fill variables, print
- Full HTTP API — every template is callable for homelab integrations
- Print history with reprint and pinning
- Freeform canvas editor (text, QR codes, barcodes, images, shapes)

## Printer setup (required)

The app talks to the printer in **raster** mode over TCP. A factory or
previously-used Brother QL-820NWB often ships configured for standalone
template printing, which will reject raster jobs with a misleading
`wrong roll type` error. Set these on the printer's LCD before first use:

- **Command Mode → Raster.** Menu → (Template/Command settings) → Command
  Mode → Raster. If it is set to `P-touch Template` or `ESC/P`, raster jobs
  fail. This is the single most common cause of prints not appearing.
- **Template Mode → Off.** Menu → Template Settings → Template Mode → Off.
  A saved template size overrides DK roll auto-detection and forces a fixed
  label size, causing `wrong roll type` on a non-matching roll.
- **Unit → mm.** Menu → Settings → Unit → mm. Cosmetic, but keeps the panel
  readout consistent with the catalog.

After changing Command Mode, reseat the DK roll (remove it, close the cover
empty so the printer reports no media, then reload) so media auto-detection
re-runs.

### Troubleshooting `wrong roll type`

If a job is rejected as `wrong roll type` even with the settings above:

- **Worn or sample rolls.** Detection depends on the plastic tabs on the
  roll's spool end-caps pressing micro-switches in the bay. Worn rolls (e.g.
  the bundled SAMPLE roll) can fail to be sensed and get rejected. Test with
  a standard DK roll that has intact end-caps.
- **Media mismatch.** The `label_media` in the request must match the roll
  physically loaded. The printer rejects a job whose declared media does not
  match what it senses.
- The network backend cannot read printer status back, so a failed print may
  still return HTTP 200 with `status: "sent"` — `sent` means *transmitted*,
  not *confirmed printed*. Watch the physical printer.

## Design docs

See [`docs/PRD.md`](docs/PRD.md) for scope, then [`docs/features/`](docs/features/) for per-feature designs.

## License

GPL-3.0. Builds on [`matmair/brother_ql-inventree`](https://github.com/matmair/brother_ql-inventree) (GPL-3.0).
