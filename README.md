# pyaota

> Multiple choice exam question manager, exam generator, and exam grader

[![Tests](https://github.com/cameronabrams/pyaota/actions/workflows/tests.yaml/badge.svg)](https://github.com/cameronabrams/pyaota/actions/workflows/tests.yaml)
[![PyPI](https://img.shields.io/pypi/v/pyaota)](https://pypi.org/project/pyaota/)
[![Docs](https://readthedocs.org/projects/pyaota/badge/?version=latest)](https://pyaota.readthedocs.io/en/latest/)

pyaota builds randomized multiple-choice and true/false exams from YAML question
banks, typesets them with a machine-readable answer sheet (bubble field, student-ID
bubbles and a QR code identifying the version), and grades the scanned sheets back
into your gradebook CSV.

- Many versions from one bank, with questions and choices shuffled per version
- Optional encryption of each version's answers in its QR code, so grading needs no key file
- Per-page graded overlays, a failed-pages report, and interactive recovery for unreadable pages
- Utilities to convert Word question exports, bundle PDFs for printing, and email graded sheets

## Install

```bash
pip install pyaota
```

You also need **xelatex** (TeX Live or MiKTeX) to build exams and **Poppler**
(`apt install poppler-utils`, `brew install poppler`, or `conda install -c conda-forge poppler`)
to grade them. Optional extras: `pyaota[interactive]` for `grade --interactive`.

## Quick start

```bash
# build two shuffled 20-question versions with answers encrypted in the QR codes
pyaota build -q examples/question_banks/simple_math.yaml \
  -n 2 -nq 20 -nc 4 -sc -sq --encode-answers-in-qr \
  --institution "Example University" --course "MATH 101" --term "Spring 2026" \
  -en "Quiz 1" -od build

# after the exam: grade the scanned answer sheets
pyaota grade -i scans.pdf -alj build/answersheet_layout.json -od graded
```

Keep `answersheet_layout.json` away from students: it holds the key that decrypts
the answers in the QR codes.

## Documentation

Full documentation — question bank schema, every subcommand, the grading
workflow and worked examples — is at <https://pyaota.readthedocs.io>.

## Development

```bash
git clone https://github.com/cameronabrams/pyaota.git
cd pyaota
pip install -e '.[test]'
pytest
```

Changes are recorded in [CHANGELOG.md](CHANGELOG.md).
