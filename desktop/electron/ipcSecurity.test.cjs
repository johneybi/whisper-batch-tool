const assert = require("node:assert/strict");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  createOutputAccessStore,
  validatePathArray,
  validateTranscriptionPayload
} = require("./ipcSecurity.cjs");

test("output access store denies files until worker output is allowlisted", () => {
  const store = createOutputAccessStore();
  const outputFile = path.join(os.tmpdir(), "meeting.srt");
  const siblingFile = path.join(os.tmpdir(), "private.txt");

  assert.throws(
    () => store.assertReadableOutputFile(outputFile),
    /File access denied/
  );

  store.addOutputFiles([outputFile]);

  assert.equal(store.assertReadableOutputFile(outputFile), path.resolve(outputFile));
  assert.equal(store.assertShellOutputTarget(path.dirname(outputFile)), path.resolve(path.dirname(outputFile)));
  assert.equal(store.assertShellOutputTarget(outputFile, { requireFile: true }), path.resolve(outputFile));
  assert.throws(
    () => store.assertReadableOutputFile(siblingFile),
    /File access denied/
  );
});

test("output access store ignores non-output file extensions", () => {
  const store = createOutputAccessStore();
  const mediaFile = path.join(os.tmpdir(), "meeting.mp4");

  store.addOutputFiles([mediaFile]);

  assert.equal(store.hasOutputFile(mediaFile), false);
  assert.throws(
    () => store.assertShellOutputTarget(mediaFile, { requireFile: true }),
    /Shell access denied/
  );
});

test("transcription payload validation normalizes safe values", () => {
  const sourceFile = path.join(os.tmpdir(), "clip.MP4");
  const outputDir = path.join(os.tmpdir(), "transcripts");

  const payload = validateTranscriptionPayload({
    files: [sourceFile],
    options: {
      model_name: "small",
      language: "",
      task: "transcribe",
      device: "auto",
      output_formats: ["TXT", "srt", "txt"],
      output_dir: outputDir,
      condition_on_previous_text: true,
      overwrite: false
    }
  });

  assert.deepEqual(payload.files, [path.resolve(sourceFile)]);
  assert.equal(payload.options.language, "");
  assert.deepEqual(payload.options.output_formats, ["txt", "srt"]);
  assert.equal(payload.options.output_dir, path.resolve(outputDir));
});

test("transcription payload validation rejects unsafe values", () => {
  assert.throws(
    () => validateTranscriptionPayload({
      files: [path.join(os.tmpdir(), "notes.txt")],
      options: { output_formats: ["txt"] }
    }),
    /not a supported media file/
  );

  assert.throws(
    () => validateTranscriptionPayload({
      files: [path.join(os.tmpdir(), "clip.wav")],
      options: { task: "delete-everything", output_formats: ["txt"] }
    }),
    /Unsupported options.task/
  );

  assert.throws(
    () => validateTranscriptionPayload({
      files: [path.join(os.tmpdir(), "clip.wav")],
      options: { output_formats: ["exe"] }
    }),
    /Unsupported output format/
  );
});

test("dropped path validation requires string arrays", () => {
  assert.deepEqual(validatePathArray([], "paths", { allowEmpty: true }), []);
  assert.throws(() => validatePathArray("C:/tmp/file.wav", "paths"), /must be an array/);
  assert.throws(() => validatePathArray([42], "paths"), /must be a string/);
});
