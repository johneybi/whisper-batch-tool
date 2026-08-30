# Product Requirements Document: Whisper Batch Transcriber (v2)

> Scope update: v1 started as batch transcription only. The focused live workspace is now an accepted product capability; see [DECISIONS.md](DECISIONS.md), [PRODUCT_EVOLUTION.md](PRODUCT_EVOLUTION.md), and GitHub [Issue #2](https://github.com/johneybi/whisper-batch-tool/issues/2).

## 1. Overview

Whisper Batch Transcriber is an Electron/React desktop GUI application that transcribes audio and video files in batches using OpenAI Whisper, with a focused live workspace for YouTube sources. The product is intended for non-technical users who need reliable local transcription output without manually managing Python, pip packages, or ffmpeg.

The official product target is the Electron app under `desktop/`. The older Tk/PyInstaller app is retained only as a legacy release path. The application packages or prepares the runtime as OS-specific distributables and provides a simple file-based workflow: add files or folders, select transcription options, start processing, and open generated output files.

## 2. Problem Statement

Users often need to transcribe long recordings, meetings, lectures, interviews, or video files, but command-line Whisper workflows are difficult for non-technical users. Existing manual workflows require Python setup, dependency management, ffmpeg installation, model selection, and output formatting.

This product reduces that friction by providing a packaged GUI app with bundled or automatically prepared ffmpeg support and common output formats.

## 3. Goals

- Enable non-technical users to batch transcribe audio/video files from a desktop GUI.
- Support common media formats through ffmpeg.
- Generate useful transcript and subtitle outputs without extra tools.
- Provide Windows and macOS distributable builds.
- Avoid requiring end users to install Python or ffmpeg manually.
- Provide a bounded YouTube live workspace with readable, persisted transcript output.
- Make release builds verifiable through simple smoke tests.

## 4. Non-Goals

- Unbounded real-time transcription or an unlimited stream dashboard. The focused live workspace is in scope with an explicit source, bounded chunking, a visible concurrency limit, and per-run stop controls.
- Cloud transcription or server-side processing.
- Collaborative transcript editing.
- Speaker diarization.
- Full media library management.
- Automatic translation quality tuning beyond Whisper's built-in `translate` task.
- App Store distribution.

## 5. Target Users

- Content creators transcribing video or audio archives.
- Researchers processing interviews or field recordings.
- Students and educators transcribing lectures.
- Office users converting meeting recordings into text.
- Korean-speaking users who want a simple local transcription workflow.

## 6. User Personas

### Non-Technical End User

Needs to drag in files, choose an output format, and receive transcript files. Does not want to install Python, ffmpeg, or command-line tools.

### Power User

Needs batch processing, multiple output formats, model choice, output folder selection, overwrite control, and device selection.

### Release Maintainer

Needs repeatable Windows/macOS builds and simple verification that the packaged app can find ffmpeg.

## 7. Core User Journey

1. User installs or opens the app from a Windows installer/ZIP or macOS DMG/ZIP.
2. User adds individual files or scans a folder recursively.
3. User selects model, language, task, device, output formats, and output folder.
4. User starts transcription.
5. App loads the selected Whisper model.
6. App processes files one by one.
7. App writes transcript outputs.
8. User opens the output folder and uses the generated files.

### Live Workspace Journey

1. User switches to the live workspace and enters a YouTube live or recorded-video URL.
2. User selects the current live point or an explicit start point and chooses a bounded chunk interval.
3. The app starts the local live engine, shows run state, and persists completed paragraphs to `data/knowledge`.
4. User can stop one run without losing completed output; the session enforces the two-run concurrency limit.

## 8. Functional Requirements

### File Input

- Users can add one or more media files.
- Users can add all supported media files from a folder.
- Folder scanning can be recursive.
- Duplicate file additions are ignored.
- The app displays the queued files and file sizes.

### Supported Media

- The app supports common audio formats, including `mp3`, `wav`, `m4a`, `flac`, `aac`, `ogg`, `opus`, `wma`, `aiff`, `alac`, and `amr`.
- The app supports common video formats, including `mp4`, `mov`, `mkv`, `webm`, `avi`, `wmv`, `m4v`, `flv`, `mpeg`, `mpg`, `m2ts`, `mts`, and `ts`.
- Unsupported extensions may still be attempted if ffmpeg can decode them.

### Transcription Options

- Users can select Whisper model: `tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3`.
- Default model is `small`.
- Users can specify language code.
- Default language is Korean (`ko`).
- Users can choose automatic language detection by clearing the language value.
- Users can choose task: `transcribe` or Whisper `translate`.
- Whisper `translate` outputs English text/subtitles only; arbitrary target-language translation requires a separate translation engine.
- Users can choose device: `auto`, `cpu`, `cuda`, or `mps`.
- Users can enable or disable Whisper previous-text context.

### Output

- Users can select one or more output formats.
- Supported output formats are `TXT`, `SRT`, `VTT`, `JSON`, and `TSV`.
- Default output formats are `TXT` and `SRT`.
- Users can choose a custom output folder.
- If no output folder is selected, files are written next to the source media.
- Existing outputs are not overwritten by default.
- When overwrite is disabled, output filename collisions create numbered variants.

### Batch Processing

- Files are processed sequentially.
- The app shows progress and status.
- The app logs major processing events.
- Users can cancel the active batch. The Electron UI terminates the active worker and marks the in-progress file as canceled.
- Failed processing displays an error message and restores the Start button.

### Live Transcription Workspace

- Users can submit a YouTube live or recorded-video URL from the live workspace.
- Recorded sources can start from an explicit point; live sources can start from the current point.
- The service processes bounded rolling chunks. The UI presets are 15/30/60 seconds; the service accepts 10–600 seconds.
- A session supports at most two active captures, and each run has an independent stop action.
- Paragraph-oriented transcript output is persisted under the configured live-engine `data/knowledge` directory.
- The repository `services/live-engine` is the default runtime. A compatible external runtime may be selected with `WHISPER_LIVE_ENGINE_ROOT`.
- Batch and live transcription must not silently compete for the same GPU runtime.

### Runtime Dependencies

- ffmpeg must be available through system PATH, bundled runtime files, or `imageio-ffmpeg`.
- The app must support a `--self-test` mode that verifies ffmpeg availability and exits with code `0` on success.
- Whisper model files may be downloaded on first use and require internet access.

## 9. Non-Functional Requirements

### Usability

- The first screen must be the usable transcription interface.
- The app should avoid requiring terminal interaction from end users.
- Controls must remain readable on macOS and Windows default themes.
- Long operations must not freeze the GUI before the main UI appears.

### Reliability

- Output writing must be deterministic and avoid accidental overwrites.
- Release artifacts must pass ffmpeg self-test.
- The app should continue processing files sequentially unless an error or cancellation occurs.

### Performance

- Runtime performance depends on Whisper model size and selected device.
- The UI should remain responsive while transcription runs in a worker thread.
- Model loading should happen once per batch when options do not change.

### Privacy

- Transcription runs locally.
- User media files are not uploaded by the application.
- Whisper model downloads may contact upstream hosts on first use.

### Distribution

- Official release artifacts should be generated from the Electron app.
- Legacy PyInstaller/Tk artifacts may be built manually for historical releases, but they are not the current product target.
- Windows Electron release artifacts should include an installer and a portable ZIP.
- macOS Electron release artifacts should include DMG and ZIP packages.
- The Electron packaging strategy must define how Python, Whisper dependencies, and ffmpeg are bundled or installed.
- macOS builds are not currently Developer ID signed or notarized, so Gatekeeper warnings are expected.

## 10. Platform Requirements

### Windows

- Release builds should run on common x64 Windows environments.
- Default Windows release should use CPU-compatible Torch for broad compatibility unless a managed CUDA runtime is explicitly selected.
- Optional CUDA runtime distribution must be treated as a separate packaging decision because it significantly changes artifact size.

### macOS

- Electron release builds should produce both DMG and ZIP artifacts.
- The app should render correctly under macOS appearance settings.
- The build should pass `--self-test`.
- Unsigned/unnotarized builds may require users to open the app through Finder's context menu.

## 11. Release Verification

### Automated or Manual Checks

- Python syntax check passes.
- Unit tests pass:

```bash
python3 -m unittest discover -s tests
```

- Electron desktop build passes:

```bash
cd desktop
npm run build
npm run smoke:render
```

- Electron worker self-test passes:

```bash
python desktop/python/worker.py self-test
python desktop/python/worker.py runtime-info
```

- Legacy macOS app self-test passes only when building the legacy PyInstaller target:

```bash
dist/WhisperBatchTranscriber.app/Contents/MacOS/WhisperBatchTranscriber --self-test
```

- macOS DMG verification passes:

```bash
hdiutil verify release/WhisperBatchTranscriber-1.1.0-macOS.dmg
```

- Legacy Windows ZIP verification passes only when building the legacy PyInstaller target:

```bat
powershell -ExecutionPolicy Bypass -File scripts\verify_release_windows.ps1
```

## 12. Success Metrics

- User can install/open the app without installing Python or ffmpeg manually.
- User can add files and complete a batch transcription.
- Default `TXT` and `SRT` outputs are generated successfully.
- Release self-test succeeds on clean target machines.
- Support requests related to missing ffmpeg or blank GUI launch are minimized.

## 13. Known Constraints

- First model use may require internet access.
- Large models can be slow and memory-intensive.
- Electron packaging is the official target, but final end-user packaging still needs a Python runtime bundling/install policy.
- macOS Gatekeeper warnings are expected until Developer ID signing and notarization are added.
- Canceling an active transcription terminates the worker process rather than gracefully unwinding Whisper internals.
- No speaker diarization or transcript editor is included.

## 14. Future Enhancements

- Developer ID signing and notarization for macOS.
- A visible install screen or first-run model download status.
- Graceful cancellation that preserves worker process state.
- Per-file success/failure summary.
- Speaker diarization option.
- User-configurable Whisper advanced parameters.
- Localization for Korean and English UI text.

## 15. Open Questions

- Should the product prioritize Korean transcription defaults or offer a first-run language choice?
- Should `large-v3` remain available by default for all users despite size and performance cost?
- Should macOS distribution invest in notarization before wider release?
- Should the legacy terminal scripts remain in the repository or be archived separately?
