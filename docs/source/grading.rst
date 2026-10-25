.. _grading:

Grading
=======

pyaota grades exams by converting a scanned PDF of answer sheets into images,
detecting fiducial marks to correct for skew and perspective, reading the QR
code that identifies the exam version, reading the student-ID bubble field, and
comparing filled answer bubbles against the answer key for that version.

Typical workflow
----------------

1. **Scan** the completed answer sheets to a single multi-page PDF (one page per student).
2. **Run** ``pyaota grade`` to process the PDF and write results.
3. **Review** any failed pages and re-run with ``--interactive`` if needed.

.. code-block:: bash

   pyaota grade \
       -i scanned.pdf \
       -k keys.csv \
       -alj answersheet_layout.json \
       -od results/ \
       -gb gradebook.csv

``-k`` is optional for exams built with ``--encode-answers-in-qr`` (see
`Encrypted answer embedding`_).  Results go to ``-od`` (default: the current
directory); each graded sheet is written as ``graded_<student id>_<version>.pdf``
showing the detected marks, the correct answers and the score.

Answer key format
-----------------

The answer-key CSV passed to ``-k`` / ``--keyfiles`` must contain a
``version_label`` column followed by one column per question (``Q1``, ``Q2``,
…).  The ``build`` command writes this file automatically alongside the
generated exam PDFs.

Example::

   version_label,Q1,Q2,Q3,Q4,Q5
   6baa9455,a,c,True,d,a
   d82c07cd,c,a,d,False,c

Version labels are the 8-digit hexadecimal labels printed on each exam and
encoded in its QR code.

``True``/``False`` values are normalized to ``a``/``b`` respectively so that
T/F questions grade correctly.

Scoring
-------

By default every question counts toward the score.  Use ``-nc`` /
``--num-counted`` to cap the number of questions that contribute to the final
score — useful when the exam contains more questions than the declared maximum
(e.g. bonus questions).

The score written to the gradebook is:

.. math::

   \text{score} = \min\left(\frac{\text{num\_correct}}{\text{num\_counted}}, 1\right) \times 100

written with one decimal place (for example ``87.5``).  ``num_counted`` must not
exceed the number of questions on the sheet.

Gradebook integration
---------------------

Pass one or more gradebook CSV files with ``-gb`` / ``--gradebooks``.  Each
file must contain a ``Student ID`` column.  pyaota matches the detected student
ID to the corresponding row and writes the following columns, adding any that
are missing:

- ``version_label`` -- exam version read from the QR code
- ``num_questions`` -- total questions on the sheet
- ``num_correct`` -- correctly answered questions
- ``score`` -- percentage score (or the column chosen by ``--score-column`` /
  ``--column-id``)
- ``status`` -- ``ok``, or the failure status of the page (see `Failed pages`_)

Each gradebook file is **rewritten in place**; keep a copy if you need the
original.  The merge follows these rules:

- **Leading zeros are ignored** when matching IDs, so a sheet bubbled
  ``00512345`` updates the gradebook row ``512345``.
- **Rows with no page in this run are left untouched**, so you can grade a
  class in several batches.
- **A failed page never overwrites an existing score.**  It records its status
  only on a row that has no score yet.
- **Duplicate pages:** if several pages read the same ID with the same version
  and score (a sheet scanned twice), one is used.  If they disagree (for
  example two students bubbled the same ID), no grade is written for that ID
  and the conflict is listed in the failed-pages report.
- **Unmatched IDs:** a graded page whose ID is in no gradebook is saved as a
  failed page with status ``unmatched_id``.

``--column-id <SUBSTRING>`` picks the score column by a case-sensitive
substring of its name, which suits LMS exports such as
``Final Exam [Total Pts: 100 Score] |3766016``.  If no column or more than one
column matches, pyaota warns and falls back to ``--score-column``.

Failed pages
------------

Pages that cannot be graded are saved as individual PDFs named
``failed_page_<NNN>_<status>[_<version or id>].pdf`` in the directory given by
``-fp`` / ``--failed-pages-dir`` (default: the output directory).  A text
report, ``failed_pages_report.txt``, lists each failed page with its reason and
saved file name.

Failure statuses:

- ``failed_find_indicials`` / ``failed_warp`` -- the corner marks could not be
  found, so the page could not be aligned
- ``failed_read_qr`` -- the QR code could not be decoded
- ``failed_read_student_id`` -- the student-ID field could not be read,
  including a column with two or more marks of similar darkness
- ``failed_read_bubblefield`` -- the answer bubbles could not be read
- ``no_qr`` -- the page was read but yielded no version label
- ``unknown_version`` -- no answer key (embedded or CSV) for the version read
  from the QR code
- ``key_length_mismatch`` -- the answer key for that version has a different
  number of questions than the answer sheet
- ``unmatched_id`` -- graded, but the student ID is in none of the gradebooks

Interactive mode
----------------

Pass ``--interactive`` to ``pyaota grade`` to enable interactive recovery at
the terminal.  When a page fails to read automatically, pyaota pauses and
prompts you to supply the missing information before moving on.  Interactive
mode displays bubble rows with matplotlib, which is an optional dependency:
``pip install 'pyaota[interactive]'``; ``--interactive`` refuses to start
without it.

.. code-block:: bash

   pyaota grade -i scanned.pdf -k keys.csv -od results/ --interactive

Four kinds of interactive prompts are issued:

**QR code unreadable**
   A message like the following is printed and you are asked for the version label::

      [Page 7] QR code could not be read (...)
        Enter exam version label for page 7 (or blank to skip): A

   If you supply a label, pyaota continues reading the student-ID and bubble
   fields for that page.  Pressing Enter (blank) skips the page and saves it to
   the failed-pages directory.

**Student ID unreadable**
   If the student-ID bubble field cannot be decoded, you are prompted::

      [Page 7] Student ID could not be read (...)
        Enter student ID for page 7 (or blank to skip): 12345678

   If you supply an ID, pyaota continues to read the answer bubbles.

**No answer key for the version**
   If the version read from the QR code has no embedded answers and is not in
   any ``-k`` keyfile, you are asked for the path to an answer-key CSV::

      [Page 7] No answer key for version '6baa9455'
        Enter path to answer-key CSV (or blank to skip):

**Blank or ambiguous answer**
   For each question where no bubble appears filled, or where two or more
   bubbles are filled with no clear winner, a matplotlib window opens showing
   that bubble row, and you are prompted at the terminal::

      Q3: enter answer (a/b/c/d) or '-' to leave blank: b

   Enter the correct choice letter to record it, or ``-`` to leave the question
   blank.  The matplotlib window closes automatically once you respond.

.. note::

   The answer prompts open a matplotlib window, so they need a graphical
   display.  If standard input is closed (end of file), each prompt is skipped
   and the page is graded as if ``--interactive`` had not been given.

Question-level statistics
-------------------------

Pass ``-qt`` / ``--question-tally`` with a CSV path to record every
student's answers.  The file has one row per student and version
(``student_id``, ``version_label``, then ``Q1``, ``Q2``, … with the answer
detected for each question, empty if blank).  If the file already exists, new
rows are added and existing ones are kept, so batches can be tallied into one
file.  Combined with ``exam_version_keys.csv`` it is the raw material for
item analysis, such as finding questions that were poorly worded or unusually
difficult.

Encrypted answer embedding
--------------------------

Pass ``--encode-answers-in-qr`` to ``pyaota build`` to encrypt and embed the
correct answers directly in each answer sheet's QR code:

.. code-block:: bash

   pyaota build -q banks/*.yaml -n 4 -nq 25 --encode-answers-in-qr ...

At build time, a random 32-byte key is generated for the exam set and stored
in ``answersheet_layout.json`` alongside the layout geometry.  Each answer
sheet's QR code then contains the version label and the encrypted answer
string rather than the version label alone.  Each version is encrypted
independently, keyed on its version label, so a student who learns the answers
to their own version (for example from a returned graded sheet) cannot use
their QR code to decrypt any other version.  Sheets built by pyaota 0.5.0,
which lacked this protection, can still be graded.

At grade time, the grader reads the key from the layout JSON, decrypts the
answers from the QR code, and grades without consulting
``exam_version_keys.csv``.  No additional flags or arguments are needed —
grading works exactly as before:

.. code-block:: bash

   pyaota grade -i scanned.pdf -alj answersheet_layout.json -od results/

The ``-k`` / ``--keyfiles`` argument becomes optional when all sheets have
embedded answers; it remains useful as a fallback for any page where the QR
could not be read and the operator supplies the version label manually in
interactive mode.

.. note::

   The security boundary is the ``answersheet_layout.json`` file.  Anyone
   who has that file can decrypt the QR codes, so it should be treated as a
   privileged document and not distributed to students.  Answer sheets without
   a corresponding layout key (e.g., from an older exam set) are graded via
   CSV lookup as usual.

Debug output
------------

Every run saves diagnostic images for each page in
``<debug dir>/page_<NNN>/`` (default debug dir: ``debug-autograder``; change it
with ``--debug-output-dir``).  They show the detected corner marks, the
straightened page, the QR region, and an overlay of bubble centers and the
marks that were read, which helps diagnose alignment or threshold problems.
