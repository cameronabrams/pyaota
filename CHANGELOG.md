# Changelog

All notable changes to pyaota will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `build --single-page` puts a short quiz on one side of one sheet: the questions on top and an answer strip across the bottom with the name line, QR code, student-ID grid and up to 10 question bubbles, whose rows line up with the ID-digit rows. The corner marks are where they are on a full answer sheet, so grading is unchanged. A version whose questions do not fit above the strip stops the build with an error naming it, instead of being clipped.
- `build --question-column-sep LENGTH` sets the gap between question columns (default `2em`, wider than before), and `--question-column-rule` draws a rule between them. Neither affects the columns of answer choices.
- `build` refuses to replace a build in its output directory whose QR codes carry encrypted answers, with or without `-ow`: every build draws a new key, so sheets already printed from the old build could no longer be graded from their QR codes. `--force` replaces it anyway.

### Changed

- The "True (T) / False (F)" label of a true/false question is on its own line, with the statement below it. On one line, a justified first line stretched badly in narrow question columns.

### Fixed

- A QR answer key that does not match the sheet now says the sheet probably came from a different build and to grade it with that build's `answersheet_layout.json`, instead of only "MAC verification failed".
- `build` with a missing question bank stopped with a traceback, after `-ow` had already deleted the output directory. It now reports the missing file before touching anything.

- **Four-across choices could overflow their column.** Whether choices go 4, 2 or 1 to a row is now decided from the actual widths: the document font size, the question column's width (including the gap), and Latin Modern Mono's exact character width for code. Before, it was a character count that ignored font size, and a `\columnsep` set for the question columns also widened the gaps between choices. Code choices up to 32 characters (was 28) now go two to a row at full width.
- LaTeX error messages in build failures are no longer cut off at 79 characters on TeX Live.
- `compile-dump` into an output directory that did not exist yet failed with `FileNotFoundError` (a 0.7.0 regression from writing LaTeX sources into the output directory).

## [0.7.0] - 2026-10-27

### Added

- `build --question-columns 2` sets the questions in two columns. Code-reading questions rarely fill the line, so this about doubles how many fit on a page: 7–8 "what does this print?" questions plus instructions fit on the front of a one-sheet quiz whose answer sheet is on the back.
- Very short choices are set four to a row instead of two by two. The choice of 4, 2 or 1 columns takes the question's width into account, so it also works in two-column layouts.

### Fixed

- **Exam LaTeX sources were written to the current directory**, not to `-od`. They contain the answer key, which made them easy to commit or hand out by mistake. They are now written to the output directory with the PDFs.
- **Builds aborted at random with "QR round-trip verification failed".** OpenCV's QR detector fails to read a few percent of valid codes (about 1 in 40 with OpenCV 5.0), so a build of many versions usually hit one. Building and grading now fall back to OpenCV's ArUco-based QR detector, which reads them.
- **Every build without `--seed` produced the same version labels**, because the default seed was 0. Each version's question selection and order are seeded by its label, so builds from the same bank in different terms gave the same labels and the same orderings. Each build now draws a random seed and logs it; `--seed` still makes a build reproducible. The answer-encryption key was always random per build.

## [0.6.1] - 2026-10-25

### Fixed

- **TeX Live builds could not find the QR code images.** The `.tex` file is compiled from the current directory while QR codes (and copied question images) are written to `-od`; MiKTeX searches the output directory for inputs but TeX Live does not, so on TeX Live the answer sheet failed to load its QR code — silently before 0.6.0, which ignored LaTeX errors. The output directory is now added to `TEXINPUTS`.
- `build` without `-q`, `-nq` or `-od` reports which are missing instead of crashing with a `TypeError`. They are not argparse-required, so `--config` can still supply them.
- `grade` writes each page's diagnostic images to its own folder (`<debug dir>/page_NNN/`); before, every page overwrote the same files, leaving only the last page's. Calling `Autograder.grade_pdf` without a debug directory no longer crashes.

## [0.6.0] - 2026-10-25

### Changed

- Depends on `opencv-python-headless` instead of `opencv-python`; pyaota uses no OpenCV GUI functions, and the headless build installs on servers and CI without system display libraries. If both are installed in one environment they conflict over `cv2`; uninstall `opencv-python`.
- `grade --interactive` needs matplotlib, which was never declared; it is now the `interactive` extra (`pip install 'pyaota[interactive]'`), and `--interactive` stops at startup with that hint if it is missing instead of crashing mid-run.
- Tests run in CI on every push to `main` and on pull requests (Python 3.10–3.13), and again before each release. New `test` extra (`pip install -e .[test]`).

### Removed

- The `tune-answersheetreader` subcommand, which always crashed (it called a reader method that does not exist). `grade` writes per-page debug overlays to its debug directory instead.
- The unused `pyaota.ocr` package, its 1.6 MB digit model (previously shipped in every wheel), and the `ocr` extra; student IDs are read from bubbles only, as before.
- Unused modules `pyaota.image.diagnose` (which could not run: it imported neither `cv2` nor a logger) and `pyaota.image.blend`.

### Security

- **QR answer encryption no longer shares one keystream across exam versions.** In 0.5.0 every version in a build was encrypted with the same keystream, so a student who learned their own version's answers (e.g. from a returned graded sheet) could recover it from their QR code and decrypt every other version from that build (such as a make-up sitting). Each version's keystream is now keyed on its version label, encryption and MAC keys are separate, and the MAC covers the version label. New QR payloads are marked `2.`; sheets printed by 0.5.0 still decrypt and grade. Rebuild any exam set whose versions have not all been administered yet.

### Fixed

- A QR code with embedded answers, read with a layout file that has no `qr_answer_key`, is graded by its version label from the answer-key CSV instead of using the whole payload as the version (whose `/` characters crashed the run when saving the failed page).

- **Wrong answer keys with shuffled choices.** Choice shuffling (`-sc`) relabeled only the `correct` field, so multiple-choice questions that give their answer as `answer:` (as `simple_javascript.yaml` does) kept the pre-shuffle letter in the answer key, the QR code and the answer-key PDF; in the documented JavaScript example 10 of 12 keys pointed at the wrong choice. Questions are now normalized when the bank is loaded: one `correct` field (from `correct`, else `answer`), multiple-choice keys matched without regard to case, and true/false strings such as `"False"` parsed as false (previously any non-empty string rendered as True). **Check any exam built with `-sc` from a bank that uses `answer:` for multiple-choice questions.**
- A question with no answer, an answer that matches no choice key, or an unknown type is now reported (with its id) when the bank is loaded, instead of crashing later or producing a wrong key.
- Choice shuffling no longer modifies the loaded bank, so a version's choice order no longer depends on which versions were built before it in the same run. With `-sc -n 2` or more, versions after the first therefore differ from what 0.5.0 produced with the same seed.
- `--config` now applies every saved value except options given on the command line. Previously options with a non-empty default (`-n`, `-nc`, `-en`, `--font-size`, …) ignored the config file, so `--save-config` then `--config` did not reproduce a run, and saved booleans overrode flags given on the command line.
- Exam name, institution, course and term are escaped for LaTeX, so `#`, `&`, `%` and `_` in them no longer break the exam or answer-key PDF.
- Unicode superscript digits (`m²`) render as superscripts instead of `\textbackslash{}textsuperscript\{2\}`; in verbatim and listings code they are kept as the Unicode character.
- Answer sheets no longer crash when the question blocks do not divide evenly into the columns (including the `make-answersheet` default of 50 questions in 3 columns, and fewer blocks than columns). Generator and grader now share one slot layout; sheets that already worked keep identical bubble positions.
- `make-answersheet` no longer requires a question list when placing bubbles.
- `grade --question-tally` no longer crashes on the first run (`NameError`) or when appending to an existing tally (`KeyError`), which also prevented the failed-pages report from being written.
- LaTeX failures are no longer silently ignored: if the final engine pass fails or produces no PDF, the build stops with the errors from the log, before the answer-key CSV is written.
- Grading no longer silently credits or overwrites the wrong student:
  - multiple marks in a student-ID column are accepted only when one is clearly darker (by `runner_up_margin`), with a warning; otherwise the ID is unreadable and the page fails (or is prompted for with `--interactive`);
  - pages that read the same student ID with different versions or scores are reported and no grade is written for that ID; identical duplicates (a sheet scanned twice) collapse to one;
  - a page that fails after its ID is read no longer blanks a score written by an earlier run;
  - a version key whose length differs from the answer sheet fails that page instead of crashing the run or grading missing questions as blank;
  - zero-padded IDs that matched a gradebook row are no longer also reported as unmatched.
- `answer_keys.pdf` is built again (the compiler required a `version` that plain documents lack), and no longer loads `xcolor` twice with clashing options.

## [0.5.0] - 2026-03-24

### Added

- **Encrypted answer embedding in QR codes** (`--encode-answers-in-qr` flag on `build`) — correct answers are encrypted and stored directly in each answer sheet's QR code. A random per-exam-set key is generated at build time and stored in `answersheet_layout.json`; the grader decrypts automatically using that file, making the answer-key CSV optional for day-of grading. Old answer sheets without embedded answers continue to work unchanged via CSV lookup.
- **Interactive grading** (`--interactive` flag on `grade`) — when a QR code, student-ID field, or answer bubble cannot be read automatically, pyaota pauses and prompts the operator at the terminal to supply the missing value. For unanswered questions a matplotlib window displays the bubble row so the operator can confirm or override the detected answer.

## [0.4.0] - 2026-03-24

### Added

- Documentation and usage examples for grading workflow.

## [0.3.0] - 2026-02-27

### Added

- **Compact MCQ choice layout** — choices are automatically arranged in two columns when all choice texts are short enough.
- **True/False question simplification** — T/F questions no longer render a separate choices block; the stem is prefixed with bold True (T) / False (F).
- **T/F correct-answer highlighting** — in `compile-dump` the correct answer for T/F questions is visually indicated with a filled circle, consistent with MCQ behavior.
- **Greedy topic redistribution** — `get_random_selection` no longer errors when a topic has fewer questions than the uniform quota; available questions are redistributed across better-stocked topics so the total count is always met.
- `--font-size {10pt,11pt,12pt}` option on `build` and `compile-dump` (default `12pt`).
- `--question-spacing <LENGTH>` option on `build` and `compile-dump` (default `24pt`).
- `--bubble-font-size <PT>` option on `build` and `make-answersheet` (default `8.0`).
- `--odd-page-answersheet` flag on `build` and `make-answersheet`.
- `--rasterize` flag on `build` and `make-answersheet`.
- Full command line echoed at DEBUG level to the diagnostic log at startup.

### Fixed

- Excess vertical space between a code-block stem and the choices list in MCQs.
- Answer sheet page always renders at 12 pt regardless of the `--font-size` setting.

## [0.2.0] - 2026-01-26

### Added

- Serialization of answer sheet layouts to JSON.

## [0.1.0] - 2026-01-26

- Initial release of pyaota.