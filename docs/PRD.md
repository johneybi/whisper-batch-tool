# Product Requirements Document: Whisper Batch Transcriber

## 1. Overview

Whisper Batch Transcriber is a desktop GUI application that transcribes audio and video files in batches using OpenAI Whisper. The product is intended for non-technical users who need reliable transcription output without manually installing Python, pip packages, or ffmpeg.

The application packages the runtime as OS-specific distributables and provides a simple file-based workflow: add files or folders, select transcription options, start processing, and open generated output files.

## 2. Problem Statement

Users often need to transcribe long recordings, meetings, lectures, interviews, or video files, but command-line Whisper workflows are difficult for non-technical users. Existing manual workflows require Python setup, dependency management, ffmpeg installation, model selection, and output formatting.

This product reduces that friction by providing a packaged GUI app with bundled or automatically prepared ffmpeg support and common output formats.

## 3. Goals

- Enable non-technical users to batch transcribe audio/video files from a desktop GUI.
- Support common media formats through ffmpeg.
- Generate useful transcript and subtitle outputs without extra tools.
- Provide Windows and macOS distributable builds.
- Avoid requiring end users to install Python or ffmpeg manually.
- Make release builds verifiable through simple smoke tests.

## 4. Non-Goals

- Real-time transcription.
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
- Users can choose task: `transcribe` or `translate`.
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
- Users can cancel the batch after the current file finishes.
- Failed processing displays an error message and restores the Start button.

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

- Windows release artifacts:
  - `WhisperBatchTranscriber-1.1.0-Windows-Setup.exe`
  - `WhisperBatchTranscriber-1.1.0-Windows-x64.zip`
- macOS release artifacts:
  - `WhisperBatchTranscriber-1.1.0-macOS.dmg`
  - `WhisperBatchTranscriber-1.1.0-macOS.zip`
- macOS builds are not currently Developer ID signed or notarized, so Gatekeeper warnings are expected.

## 10. Platform Requirements

### Windows

- Release builds should run on common x64 Windows environments.
- Default Windows build should use CPU-compatible Torch for broad compatibility.
- Optional CUDA build can be produced by setting `WHISPER_RELEASE_TORCH=cuda`.

### macOS

- Release builds should produce both DMG and ZIP artifacts.
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

- macOS app self-test passes:

```bash
dist/WhisperBatchTranscriber.app/Contents/MacOS/WhisperBatchTranscriber --self-test
```

- macOS DMG verification passes:

```bash
hdiutil verify release/WhisperBatchTranscriber-1.1.0-macOS.dmg
```

- Windows ZIP verification passes:

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
- macOS Gatekeeper warnings are expected until Developer ID signing and notarization are added.
- The current cancel behavior stops after the current file, not during an active Whisper transcription call.
- No speaker diarization or transcript editor is included.

## 14. Future Enhancements

- Developer ID signing and notarization for macOS.
- A visible install screen or first-run model download status.
- In-progress transcription cancellation.
- Drag-and-drop file support.
- Per-file success/failure summary.
- Output preview panel.
- Speaker diarization option.
- User-configurable Whisper advanced parameters.
- Localization for Korean and English UI text.

## 15. Open Questions

- Should the product prioritize Korean transcription defaults or offer a first-run language choice?
- Should `large-v3` remain available by default for all users despite size and performance cost?
- Should macOS distribution invest in notarization before wider release?
- Should the legacy terminal scripts remain in the repository or be archived separately?
