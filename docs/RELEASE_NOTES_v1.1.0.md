# Whisper Batch Transcriber 1.1.0

## Highlights

- Added macOS release packaging with DMG and ZIP outputs.
- Added ffmpeg runtime validation so packaged apps can be checked with `--self-test`.
- Added focused regression tests for output-file generation behavior.
- Added a PRD document for product scope, workflows, and release risks.
- Added an Electron/React desktop UI prototype under `desktop/` for the next-generation interface.

## Downloads

- `WhisperBatchTranscriber-1.1.0-macOS.dmg`: recommended macOS installer-style package.
- `WhisperBatchTranscriber-1.1.0-macOS.zip`: alternate macOS app archive.

## Notes

- The current macOS build is unsigned and not notarized. Gatekeeper may show an "unidentified developer" warning on first launch.
- Windows release artifacts are supported by the build scripts, but are not attached to this macOS-generated release.
- The Electron/React UI is included in the repository as a prototype. The packaged release still uses the Python/Tk desktop app.

## Validation

- `python3 -m unittest discover -s tests`
- `npm run build` in `desktop/`
- `.release-venv/bin/python desktop/python/worker.py self-test`
