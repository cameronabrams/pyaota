Usage
=====

pyaota is invoked via the ``pyaota`` command-line tool. All functionality is
accessed through subcommands.

.. code-block:: bash

   pyaota <subcommand> [options]

Boolean options also have a ``--no-`` form (``--shuffle-choices`` /
``--no-shuffle-choices``), useful for overriding a value loaded with
``--config``.  Note that ``-nc`` and ``-sc`` mean different things in ``build``
(answer-sheet columns, shuffle choices) and ``grade`` (questions counted,
score column).

Global options
--------------

``--config <path>``
   Load arguments from a YAML configuration file.  Every value in the file is
   used except options also given on the command line, which take precedence.

``--save-config <path>``
   Save the current arguments to a YAML file for later reuse with ``--config``.

``-b`` / ``--banner``
   Display a banner message at startup.

``--logging-level {None,info,debug,warning}``
   Set the diagnostic logging level (default: ``debug``).

``-l`` / ``--log <path>``
   Path to the diagnostic log file (default: ``pyaota-diagnostics.log``).

Subcommands
-----------

build
~~~~~

Generate one or more randomized exam versions from YAML question banks.

.. code-block:: bash

   pyaota build -q banks/*.yaml -n 4 -nq 25 -t topic1 topic2 \
       -od exams/ --seed 42

Key options:

- ``-q`` / ``--question-banks`` -- paths to YAML question bank files (required)
- ``-nq`` / ``--num-questions`` -- questions per exam (required)
- ``-od`` / ``--output-dir`` -- output directory (required)
- ``-n`` / ``--num-exams`` -- number of exam versions to generate (default: ``1``)
- ``-t`` / ``--topics`` -- topics to draw questions from, spread evenly; names
  must match the bank's topics exactly (unknown names are ignored)
- ``--seed`` -- seed for the version labels (default: a new random seed for
  each build, written to the log).  Each version's question selection and order
  are derived from its label, so the same seed and options rebuild the same
  exams
- ``-sq`` / ``--shuffle-questions`` -- shuffle question order per version
- ``-sc`` / ``--shuffle-choices`` -- shuffle answer choices per version
- ``-en`` / ``--exam-name`` -- exam title used in the header
- ``-if`` / ``--instructions-file`` -- custom LaTeX instructions file
- ``-pf`` / ``--pagestyles-file`` -- custom LaTeX page-styles file
- ``--institution``, ``--course``, ``--term`` -- header text (defaults:
  ``Drexel University``, ``ENGR-131``, ``202526``)
- ``-en`` defaults to ``Exam``
- ``--encode-answers-in-qr`` -- encrypt the correct answers into each answer
  sheet's QR code; when set, ``pyaota grade`` does not require a ``-k``
  keyfile — the grader decrypts the answers directly from the scanned QR.
  The encryption key is stored in ``answersheet_layout.json``.
- ``--cleanup`` -- remove intermediate LaTeX files after compilation
- ``-ow`` / ``--overwrite`` -- **delete** the output directory and everything in
  it before building; without it, an existing directory is reused (with a
  warning)
- ``--font-size {10pt,11pt,12pt}`` -- document font size (default: ``12pt``)
- ``--question-spacing <LENGTH>`` -- vertical space between questions as a LaTeX
  length, e.g. ``24pt`` or ``1cm`` (default: ``24pt``)
- ``--question-columns {1,2}`` -- set the questions in one or two columns
  (default: ``1``).  Two columns suit short code-reading questions: a code
  block rarely fills the line, so one column leaves half the page blank.  With
  the answer sheet printed on the back, two columns fit 7–8 "what does this
  print?" questions plus a short instruction paragraph on one side at 11pt;
  pass ``-if`` with instructions that do not end in ``\clearpage``.
- ``--single-page`` -- put the questions and the answer area on one page: a
  strip across the bottom holds the name line, the QR code, the student-ID grid
  and one column of question bubbles, and the questions are set above it.  For
  short quizzes of at most 10 questions; it pairs well with
  ``--question-columns 2``.  Without ``-if`` it uses short instructions that
  fit the page.  If any version's questions do not fit above the strip, the
  build stops and names that version; nothing is clipped.  The sheets are
  graded exactly like two-page ones.  About 6 short code-reading questions fit
  at 11pt; check longer ones by building.
- ``--question-column-sep <LENGTH>`` -- gap between question columns as a LaTeX
  length (default: ``2em``)
- ``--question-column-rule`` -- draw a rule between question columns
- ``--bubble-font-size <PT>`` -- absolute font size in points for answer bubble
  labels (default: ``8.0``); independent of ``--font-size``
- ``--odd-page-answersheet`` -- force the answer sheet to start on an odd-numbered
  page by inserting a blank filler page when needed (useful for double-sided
  printing)
- ``--rasterize`` -- rasterize output PDFs at 300 DPI after compilation for
  improved printer compatibility
- ``--use-listings-from <TEX_FILE>`` -- path to a ``.tex`` file defining an
  ``lstdefinestyle``; enables ``listings``/``\inl`` rendering instead of
  verbatim for code in questions
- ``--balance-difficulty`` -- select questions proportionally across difficulty
  levels (1–5) so each exam version has roughly the same difficulty
  distribution; questions without a ``difficulty`` attribute are treated as
  difficulty 1
- ``-nc`` / ``--num-cols`` -- number of bubble columns on the answer sheet
  (default: ``3``)

Output, in ``-od``: ``exam-<version>.pdf`` per version (questions followed by
the answer sheet), ``exam_version_keys.csv``, ``answer_keys.pdf``,
``answersheet_layout.json`` (needed for grading) and ``qr_<version>.png``.  The
LaTeX sources ``exam-<version>.tex`` are written there too and kept unless
``--cleanup`` is given; they contain the answer key, so keep them from
students.

compile-dump
~~~~~~~~~~~~

Compile every question from one or more banks into a single PDF document,
useful for review and proofreading.

.. code-block:: bash

   pyaota compile-dump -q banks/*.yaml -od dump/

Key options:

- ``-q`` / ``--question-banks`` -- paths to YAML question bank files
- ``-od`` / ``--output-dir`` -- output directory (default: current directory)
- ``-if`` / ``--instructions-file`` -- custom LaTeX instructions
- ``-pf`` / ``--pagestyles-file`` -- custom LaTeX page-styles file
- ``--institution``, ``--course``, ``--term`` -- header text (same defaults as
  ``build``)
- ``--font-size {10pt,11pt,12pt}`` -- document font size (default: ``12pt``)
- ``--question-spacing <LENGTH>`` -- vertical space between questions (default: ``24pt``)
- ``--use-listings-from <TEX_FILE>`` -- set code with ``listings`` (see ``build``)
- ``--keep-latex`` -- keep the intermediate ``.tex`` file

The output is ``banks_full_dump-0.pdf``, with each question's id and the
correct answer marked.

grade
~~~~~

Automatically grade a scanned PDF of answer sheets.

.. code-block:: bash

   pyaota grade -i scanned.pdf -alj answersheet_layout.json -od results/

Key options:

- ``-i`` / ``--input-pdf`` -- PDF of scanned answer sheets (needed)
- ``-k`` / ``--keyfiles`` -- CSV answer key file(s); optional when answers are
  embedded in the QR code via ``--encode-answers-in-qr``
- ``-alj`` / ``--answersheet-layout-json`` -- the ``answersheet_layout.json``
  written by ``build`` (needed; also carries the QR decryption key when
  ``--encode-answers-in-qr`` was used)
- ``-od`` / ``--output-dir`` -- output directory for graded sheets (default:
  current directory)
- ``--debug-output-dir`` -- directory for per-page diagnostic images (default:
  ``debug-autograder``)
- ``-fp`` / ``--failed-pages-dir`` -- directory for unreadable pages and the
  failed-pages report (default: ``-od``)
- ``-gb`` / ``--gradebooks`` -- gradebook CSV file(s) to update
- ``-sc`` / ``--score-column`` -- gradebook column name for scores (default:
  ``'score'``)
- ``--column-id <SUBSTRING>`` -- substring matched against gradebook column
  names to identify the score column (e.g. ``'Final'`` matches
  ``'Final Exam [Total Pts: 100 Score] |3766016'``); takes precedence over
  ``--score-column`` when a unique match is found
- ``-nc`` / ``--num-counted`` -- number of questions counted toward score
  (default: all)
- ``-qt`` / ``--question-tally`` -- CSV recording each student's answers
- ``--interactive`` -- pause and prompt for manual input when a QR code, student
  ID or answer cannot be read, and for a keyfile when a version has no answer
  key; needs ``pip install 'pyaota[interactive]'``; see :doc:`grading`

make-answersheet
~~~~~~~~~~~~~~~~

Generate a blank answer sheet PDF.

.. code-block:: bash

   pyaota make-answersheet -nq 50 -nc 3 -o answersheet

This writes ``answersheet-SAMPLE.pdf`` with a sample QR code.

Key options:

- ``-o`` / ``--output-pdf`` -- base name of the output file; ``-SAMPLE.pdf`` is
  appended (default: ``answersheet``)
- ``-nq`` / ``--num-questions`` -- number of questions (default: ``50``)
- ``-nc`` / ``--num-cols`` -- number of bubble columns (default: ``3``)
- ``-od`` / ``--output-dir`` -- output directory (default: current directory)
- ``-idl`` / ``--student-id-num-digits`` -- digits in the student ID field
  (default: ``8``)
- ``--bubble-font-size <PT>`` -- absolute font size in points for bubble labels
  (default: ``8.0``)
- ``--odd-page-answersheet`` -- force the sheet to start on an odd-numbered page
- ``--rasterize`` -- rasterize the output PDF at 300 DPI for printer compatibility

bundle
~~~~~~

Bundle multiple PDF files from a directory into uniform-sized bundles for
printing.

.. code-block:: bash

   pyaota bundle -i exams/ -n 30 -od bundles/ --co-bundle

Key options:

- ``-i`` / ``--input-dir`` -- directory of PDFs to bundle
- ``-n`` / ``--bundle-size`` -- documents per bundle
- ``-od`` / ``--output-dir`` -- output directory (default: ``bundles``); bundles
  are named ``bundle_NNN.pdf``
- ``--co-bundle`` -- also create a PDF of the last page from each document

return
~~~~~~

Email graded answer sheets and exam PDFs to students via Microsoft Outlook.
This works only on Windows with Outlook installed and the ``pywin32`` package
(``pip install pywin32``), which is not installed with pyaota.  Each student's
graded sheet is found by name (``graded_<id>_<version>.pdf``) and sent with
their exam version's PDF.

.. code-block:: bash

   pyaota return -gb gradebook.csv -gd graded/ -ed exams/ --dry-run

Key options:

- ``-gb`` / ``--gradebooks`` -- gradebook CSV file(s)
- ``-gd`` / ``--graded-dir`` -- directory of graded answer sheet PDFs
- ``-ed`` / ``--exams-dir`` -- directory of exam version PDFs
- ``--email-column`` -- gradebook column with email/username (default:
  ``Username``)
- ``--email-suffix`` -- suffix to append (default: ``@drexel.edu``; use ``''``
  if the column holds full addresses)
- ``--subject`` -- email subject line (default: ``Your graded exam``)
- ``--body`` -- email body text
- ``--dry-run`` -- preview without sending
- ``--sleep-seconds`` -- pause between emails (default: ``0.5``)

convert
~~~~~~~

Convert a ZyBooks-exported ZIP file (containing QTI XML or Word documents)
into a YAML question bank.

.. code-block:: bash

   pyaota convert -i export.zip -o questions.yaml

Key options:

- ``-i`` / ``--input-zip`` -- path to ZyBooks export ZIP
- ``-o`` / ``--output-yaml`` -- output YAML question bank path

The YAML file this generates needs some careful manual cleanup to be usable, but it can save time compared to starting from scratch.
