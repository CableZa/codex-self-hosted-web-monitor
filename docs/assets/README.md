# Repository Assets

This folder contains the README logo and GitHub social preview artwork.

`dashboard-preview.svg` and `dashboard-preview.png` are fictionalized demo screenshots. Keep local account data out of these files.

Use `rsvg-convert` to rasterize SVG assets when PNG output is needed:

```sh
rsvg-convert -w 1280 -h 640 docs/assets/social-preview.svg -o docs/assets/social-preview.png
rsvg-convert -w 1280 -h 1120 docs/assets/dashboard-preview.svg -o docs/assets/dashboard-preview.png
```

Do not use `sips` for these SVG conversions. On this macOS install, `sips` can identify the files as SVG but fails to extract a raster image.
