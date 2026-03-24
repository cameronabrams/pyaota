Usage
=====

pyaota is invoked via the ``pyaota`` command-line tool. All functionality is
accessed through subcommands.

.. code-block:: bash

   pyaota <subcommand> [options]

Global options
--------------

``--config <path>``
   Load arguments from a YAML configuration file.

``--save-config <path>``
   Save the current arguments to a YAML file for later reuse.

``-b`` / ``--banner``
   Display a banner message at startup.

``--logging-level {info,debug,warning}``
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

- ``-q`` / ``--question-banks`` -- paths to YAML question bank files
- ``-n`` / ``--num-exams`` -- number of exam versions to generate
- ``-nq`` / ``--num-questions`` -- questions per exam
- ``-t`` / ``--topics`` -- topics to draw questions from
- ``-od`` / ``--output-dir`` -- output directory
- ``--seed`` -- random seed for reproducible generation
- ``-sq`` / ``--shuffle-questions`` -- shuffle question order per version
- ``-sc`` / ``--shuffle-choices`` -- shuffle answer choices per version
- ``-en`` / ``--exam-name`` -- exam title used in the header
- ``-if`` / ``--instructions-file`` -- custom LaTeX instructions file
- ``-pf`` / ``--pagestyles-file`` -- custom LaTeX page-styles file
- ``--institution``, ``--course``, ``--term`` -- metadata for headers
- ``--encode-answers-in-qr`` -- encrypt the correct answers into each answer
  sheet's QR code; when set, ``pyaota grade`` does not require a ``-k``
  keyfile — the grader decrypts the answers directly from the scanned QR.
  The encryption key is stored in ``answersheet_layout.json``.
- ``--cleanup`` -- remove intermediate LaTeX files after compilation
- ``-ow`` / ``--overwrite`` -- overwrite output directory if it exists
- ``--font-size {10pt,11pt,12pt}`` -- document font size (default: ``12pt``)
- ``--question-spacing <LENGTH>`` -- vertical space between questions as a LaTeX
  length, e.g. ``24pt`` or ``1cm`` (default: ``24pt``)
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

compile-dump
~~~~~~~~~~~~

Compile every question from one or more banks into a single PDF document,
useful for review and proofreading.

.. code-block:: bash

   pyaota compile-dump -q banks/*.yaml -od dump/

Key options:

- ``-q`` / ``--question-banks`` -- paths to YAML question bank files
- ``-od`` / ``--output-dir`` -- output directory
- ``-if`` / ``--instructions-file`` -- custom LaTeX instructions
- ``--institution``, ``--course``, ``--term`` -- metadata
- ``--font-size {10pt,11pt,12pt}`` -- document font size (default: ``12pt``)
- ``--question-spacing <LENGTH>`` -- vertical space between questions (default: ``24pt``)

grade
~~~~~

Automatically grade a scanned PDF of answer sheets.

.. code-block:: bash

   pyaota grade -i scanned.pdf -alj answersheet_layout.json -od results/

Key options:

- ``-i`` / ``--input-pdf`` -- PDF of scanned answer sheets
- ``-k`` / ``--keyfiles`` -- CSV answer key file(s); optional when answers are
  embedded in the QR code via ``--encode-answers-in-qr``
- ``-alj`` / ``--answersheet-layout-json`` -- answer sheet layout JSON (required;
  also carries the QR decryption key when ``--encode-answers-in-qr`` was used)
- ``-od`` / ``--output-dir`` -- output directory for graded results
- ``--debug-output-dir`` -- directory for debug overlay images
- ``-fp`` / ``--failed-pages-dir`` -- directory for unreadable pages
- ``-gb`` / ``--gradebooks`` -- gradebook CSV file(s) to update
- ``-sc`` / ``--score-column`` -- gradebook column name for scores (default:
  ``'score'``)
- ``--column-id <SUBSTRING>`` -- substring matched against gradebook column
  names to identify the score column (e.g. ``'Final'`` matches
  ``'Final Exam [Total Pts: 100 Score] |3766016'``); takes precedence over
  ``--score-column`` when a unique match is found
- ``-nc`` / ``--num-counted`` -- number of questions counted toward score
- ``-qt`` / ``--question-tally`` -- output CSV for question-level statistics
- ``--interactive`` -- pause and prompt for manual input when a QR code, student ID,
  or bubble fill cannot be read automatically; if a QR-encoded answer key cannot
  be decrypted, also prompts for a fallback keyfile CSV; see :doc:`grading` for details

make-answersheet
~~~~~~~~~~~~~~~~

Generate a blank answer sheet PDF.

.. code-block:: bash

   pyaota make-answersheet -nq 50 -nc 3 -o answersheet

Key options:

- ``-o`` / ``--output-pdf`` -- output PDF path
- ``-nq`` / ``--num-questions`` -- number of questions
- ``-nc`` / ``--num-cols`` -- number of bubble columns
- ``-od`` / ``--output-dir`` -- output directory
- ``-idl`` / ``--student-id-num-digits`` -- digits in the student ID field
- ``--bubble-font-size <PT>`` -- absolute font size in points for bubble labels
  (default: ``8.0``)
- ``--odd-page-answersheet`` -- force the sheet to start on an odd-numbered page
- ``--rasterize`` -- rasterize the output PDF at 300 DPI for printer compatibility

tune-answersheetreader
~~~~~~~~~~~~~~~~~~~~~~

Generate a diagnostic overlay image to visually verify that the answer sheet
reader parameters are correctly aligned.

.. code-block:: bash

   pyaota tune-answersheetreader -i sample.pdf -nq 50 -nc 3

Key options:

- ``-i`` / ``--sample-pdf`` -- sample PDF for tuning
- ``-nq`` / ``--num-questions`` -- number of questions
- ``-nc`` / ``--num-cols`` -- number of columns
- ``-o`` / ``--output-image`` -- output overlay image path

bundle
~~~~~~

Bundle multiple PDF files from a directory into uniform-sized bundles for
printing.

.. code-block:: bash

   pyaota bundle -i exams/ -n 30 -od bundles/ --co-bundle

Key options:

- ``-i`` / ``--input-dir`` -- directory of PDFs to bundle
- ``-n`` / ``--bundle-size`` -- documents per bundle
- ``-od`` / ``--output-dir`` -- output directory
- ``--co-bundle`` -- also create a PDF of the last page from each document

return
~~~~~~

Email graded answer sheets and exam PDFs to students via Microsoft Outlook.

.. code-block:: bash

   pyaota return -gb gradebook.csv -gd graded/ -ed exams/ --dry-run

Key options:

- ``-gb`` / ``--gradebooks`` -- gradebook CSV file(s)
- ``-gd`` / ``--graded-dir`` -- directory of graded answer sheet PDFs
- ``-ed`` / ``--exams-dir`` -- directory of exam version PDFs
- ``--email-column`` -- gradebook column with email/username
- ``--email-suffix`` -- suffix to append (e.g., ``@drexel.edu``)
- ``--subject`` -- email subject line
- ``--body`` -- email body text
- ``--dry-run`` -- preview without sending

convert
~~~~~~~

Convert a ZyBooks-exported ZIP file (containing QTI XML or Word documents)
into a YAML question bank.

.. code-block:: bash

   pyaota convert -i export.zip -o questions.yaml

Key options:

- ``-i`` / ``--input-zip`` -- path to ZyBooks export ZIP
- ``-o`` / ``--output-yaml`` -- output YAML question bank path
