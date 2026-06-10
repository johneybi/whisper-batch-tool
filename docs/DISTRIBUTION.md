# Distribution Strategy

## Official Product Target

The official desktop product target is the Electron/React app under `desktop/`.

The Python transcription core remains shared:

- `transcriber_core.py` owns Whisper execution, ffmpeg preparation, and output writers.
- `desktop/python/worker.py` is the Electron-facing worker process.
- `whisper_gui.py` is a legacy Tk GUI retained for historical PyInstaller releases.

## Repository Policy

Use the existing GitHub repository.

- Keep issue history, release history, docs, and the shared Python core in one place.
- Treat `main` as the Electron product line.
- Keep legacy PyInstaller files available, but label them explicitly as legacy.
- Do not create new official GitHub Releases from the legacy workflow unless the release is intentionally marked as legacy.

## Release Policy

Until Electron packaging is complete, GitHub Release artifacts should not be generated from the old PyInstaller workflow by tag push.

The legacy workflow is manual-only and names artifacts as legacy. This prevents an old Tk build from being confused with the current Electron app.

## CI Policy

The default CI path should validate the Electron product target:

- Python unit tests
- Electron worker self-test
- Electron renderer build
- Electron smoke render

## Next Packaging Decisions

The next release-quality decision is how the Electron app will carry Python and model dependencies:

1. Bundle a managed Python runtime with the Electron app.
2. Install a private runtime on first launch.
3. Require a user-selected external Python runtime for developer builds only.

For end-user distribution, option 1 or 2 is required. Option 3 is acceptable only for development.
