# v1.5 adaptive compression build status

Status: **PASS**

- Version: `1.5.0`
- Source commit: `8bdebf920345a0d3278ce17c712c38547f815008`
- Source Apple Silicon build run: `31309514252`
- Release workflow run: `31309605239`
- Finalized Artifact ID: `9036980355`
- DMG SHA-256: `24f732d69c906b4303a1f531ef3bfa8218d5f282d2b94bc8feed65cd5be92b6a`
- App ZIP SHA-256: `114f8dfab5b60e6899fc06eae735650736e6259401926dbf4ba4ab876e2f526f`
- PNG: OxiPNG 10.1.1 arm64 + adaptive candidate selection
- JPEG: MozJPEG lossless + decoded pixel verification
- Scan preprocessing: explicit opt-in, Pillow-only
- Verified: adaptive compression CI passed; full EPUB/CBZ/MOBI/App/DMG CI passed; deep codesign and final DMG verification passed.
