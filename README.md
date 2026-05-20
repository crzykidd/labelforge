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

## Design docs

See [`docs/PRD.md`](docs/PRD.md) for scope, then [`docs/features/`](docs/features/) for per-feature designs.

## License

GPL-3.0. Builds on [`matmair/brother_ql-inventree`](https://github.com/matmair/brother_ql-inventree) (GPL-3.0).
