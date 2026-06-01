# Whisper Batch Transcriber for macOS

This folder contains legacy macOS helper scripts from the earlier terminal-only
tool. The current supported macOS app is the GUI application built from the
project root.

## Recommended Distribution

Build the macOS release from the project root:

```bash
chmod +x build_macos.sh scripts/build_release_macos.sh
./build_macos.sh
```

The build creates:

- `release/WhisperBatchTranscriber-1.1.0-macOS.dmg`
- `release/WhisperBatchTranscriber-1.1.0-macOS.zip`

End users should install the DMG or unzip the ZIP and run the app. They do not
need to install Python or ffmpeg separately.

## Development Run

For local development from the project root:

```bash
chmod +x install_gui.sh run_gui.sh
./install_gui.sh
./run_gui.sh
```

## Legacy Scripts

The scripts in this `mac/` folder are kept only for the old terminal workflow.
They are not the release path described in the root README.
