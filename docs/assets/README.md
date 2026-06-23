# Repository Assets

This folder contains the README logo and GitHub social preview artwork.

`dashboard-preview.png` and `dashboard-preview-dark.png` are rendered from the real dashboard with deterministic demo API data. Keep local account data out of these files.

Regenerate the dashboard previews from the repo root:

```sh
npm run docs:preview
```

Use `rsvg-convert` to rasterize SVG social preview assets when PNG output is needed:

```sh
rsvg-convert -w 1280 -h 640 docs/assets/social-preview.svg -o docs/assets/social-preview.png
```

Do not use `sips` for SVG conversions. On this macOS install, `sips` can identify the files as SVG but fails to extract a raster image.
