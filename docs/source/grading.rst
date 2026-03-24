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

Answer key format
-----------------

The answer-key CSV passed to ``-k`` / ``--keyfiles`` must contain a
``version_label`` column followed by one column per question (``Q1``, ``Q2``,
…).  The ``build`` command writes this file automatically alongside the
generated exam PDFs.

Example::

   version_label,Q1,Q2,Q3,Q4,Q5
   A,a,c,b,d,a
   B,c,a,d,b,c

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

   \text{score} = \frac{\text{num\_correct}}{\text{num\_counted}} \times 100

Gradebook integration
---------------------

Pass one or more gradebook CSV files with ``-gb`` / ``--gradebooks``.  Each
file must contain a ``Student ID`` column.  pyaota matches the detected student
ID to the corresponding row and writes the following columns:

- ``version_label`` -- exam version read from the QR code
- ``num_questions`` -- total questions on the sheet
- ``num_correct`` -- correctly answered questions
- ``score`` -- percentage score (or the column named by ``--score-column``)
- ``status`` -- ``ok``, ``no_key``, or ``failed``

Failed pages
------------

Pages that cannot be fully read are saved as individual PDFs in the directory
specified by ``-fp`` / ``--failed-pages-dir`` (defaults to the output
directory).  A companion ``failed_pages_report.csv`` is written listing the
page index, failure reason, and any data that was recovered.

Common failure modes:

- ``failed_read_qr`` -- QR code too damaged or obscured to decode
- ``failed_read_student_id`` -- student-ID bubble field could not be read
- ``failed_read_bubblefield`` -- answer bubble region could not be processed
- ``no_key`` -- QR code decoded but no answer key exists for that version label

Interactive mode
----------------

Pass ``--interactive`` to ``pyaota grade`` to enable interactive recovery at
the terminal.  When a page fails to read automatically, pyaota pauses and
prompts you to supply the missing information before moving on.

.. code-block:: bash

   pyaota grade -i scanned.pdf -k keys.csv -od results/ --interactive

Three kinds of interactive prompts are issued:

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

**No bubble fill detected**
   For each question where no bubble appears filled, a matplotlib window opens
   showing a cropped view of that bubble row, and you are prompted at the
   terminal::

      Q3: enter answer (a/b/c/d) or '-' to leave blank: b

   Enter the correct choice letter to record it, or ``-`` to leave the question
   blank.  The matplotlib window closes automatically once you respond.

.. note::

   Interactive mode requires a graphical display for the bubble-level prompts
   (matplotlib is used).  On headless servers only the QR-code and student-ID
   prompts will appear; bubble prompts are silently skipped when stdin is not
   a TTY.

Question-level statistics
-------------------------

Pass ``-qt`` / ``--question-tally`` with a CSV path to write a per-question
summary after grading.  Each row contains the question number, how many
students answered each choice, and how many answered correctly.  This is
useful for identifying questions that were poorly worded or unusually difficult.

Encrypted answer embedding
--------------------------

Pass ``--encode-answers-in-qr`` to ``pyaota build`` to encrypt and embed the
correct answers directly in each answer sheet's QR code:

.. code-block:: bash

   pyaota build -q banks/*.yaml -n 4 -nq 25 --encode-answers-in-qr ...

At build time, a random 32-byte key is generated for the exam set and stored
in ``answersheet_layout.json`` alongside the layout geometry.  Each answer
sheet's QR code then contains the version label and the encrypted answer
string rather than the version label alone.

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

Pass ``--debug-output-dir`` to save annotated images for every processed page.
The overlay draws detected fiducials, bubble centers, fill percentages, and the
decoded QR/student-ID values, which helps diagnose alignment or threshold
issues.
