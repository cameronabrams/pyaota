# Changelog

All notable changes to pyaota will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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