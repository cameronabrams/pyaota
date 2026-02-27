.. _examples:

Examples
========

This page walks through several concrete examples using the question banks
provided in ``examples/question_banks/``.  All commands below can be run
from the root of the repository with the package installed.

----

Math quiz (MCQ only)
--------------------

The ``simple_math.yaml`` bank contains 120 arithmetic questions spread across
four topics: *integer addition*, *integer subtraction*, *integer multiplication*,
and *integer division*.

The following command generates **two randomised versions** of a 20-question
quiz (5 questions per topic) with a 4-column answer sheet:

.. code-block:: bash

   pyaota build \
     -q examples/question_banks/simple_math.yaml \
     -n 2 -nq 20 -nc 4 \
     -t "integer addition" "integer subtraction" \
        "integer multiplication" "integer division" \
     -od examples/generated/math_exam \
     --seed 1 \
     --institution "Example University" \
     --course "MATH-101" --term "Spring 2026" \
     -en "Quiz 1" \
     --cleanup --odd-page-answersheet

Output files in ``examples/generated/math_exam/``:

- ``exam-<version>.pdf`` — one PDF per exam version (questions + answer sheet)
- ``exam_version_keys.csv`` — answer key for every version
- ``answer_keys-AnswerKeys.pdf`` — printable answer-key summary
- ``answersheet_layout.json`` — machine-readable layout used by the grader

**Instructions page and first questions page of a generated math quiz:**

.. image:: _static/examples/exam_spread.png
   :width: 100%
   :align: center
   :alt: Instructions page (left) and first questions page (right) of a Math-101 quiz

----

History exam (MCQ + True/False)
---------------------------------

The ``simple_history.yaml`` bank mixes MCQ and True/False questions across
eight topics.  This example draws 4 questions from each of four topics,
producing two randomised 16-question versions:

.. code-block:: bash

   pyaota build \
     -q examples/question_banks/simple_history.yaml \
     -n 2 -nq 16 -nc 4 \
     -t "Renaissance history" "American Revolution" \
        "French Revolution" "New World Explorers" \
     -od examples/generated/history_exam \
     --seed 42 \
     --institution "Example University" \
     --course "HIST-201" --term "Spring 2026" \
     -en "Midterm" \
     --cleanup --odd-page-answersheet

True/False questions are rendered with a bold ``True (T) / False (F)`` prefix
instead of a separate choices list, keeping the exam compact.

**Instructions page and first questions page of a generated history midterm:**

.. image:: _static/examples/history_spread.png
   :width: 100%
   :align: center
   :alt: Instructions page (left) and first questions page (right) of a HIST-201 midterm

----

Programming quiz (code-block stems)
-------------------------------------

The ``simple_javascript.yaml`` bank contains questions whose stems include
fenced code blocks.  pyaota renders these using the ``lstlisting`` environment,
making it easy to ask students to interpret or debug code snippets.

.. code-block:: bash

   pyaota build \
     -q examples/question_banks/simple_javascript.yaml \
     -n 1 -nq 15 -nc 3 \
     -t "Basics" "Data types" "Arrays" \
     -od examples/generated/js_exam \
     --seed 7 \
     --institution "Example University" \
     --course "CS-110" --term "Spring 2026" \
     -en "Lab Quiz" \
     --cleanup --odd-page-answersheet --font-size 11pt

**Instructions page and first questions page of a generated JavaScript quiz:**

.. image:: _static/examples/js_spread.png
   :width: 100%
   :align: center
   :alt: Instructions page (left) and first questions page (right) of a CS-110 lab quiz with code-block stems

----

Compile-dump (review / proofreading)
--------------------------------------

The ``compile-dump`` subcommand renders every question in a bank into a single
PDF, with the correct answer highlighted.  This is useful for reviewing and
proofreading your question banks before exam day.

.. code-block:: bash

   pyaota compile-dump \
     -q examples/question_banks/simple_science.yaml \
     -od examples/generated/science_dump \
     --institution "Example University" \
     --course "SCI-101" --term "Spring 2026"

The output PDF shows each question with the correct choice circled.

----

Blank answer sheet
-------------------

You can generate a standalone blank answer sheet without building a full exam.
This is useful for printing spares or for a different question count than the
default:

.. code-block:: bash

   pyaota make-answersheet \
     -nq 20 -nc 4 -o answersheet_20q \
     -od examples/generated/answersheet

**Blank 20-question answer sheet:**

.. image:: _static/examples/blank_answersheet.png
   :width: 80%
   :align: center
   :alt: Blank 20-question answer sheet with 4 bubble columns

----

Answer keys summary
--------------------

After a ``build`` run, pyaota produces a printable answer-key PDF listing every
version with its correct answers, suitable for use at the grading station:

.. image:: _static/examples/answer_keys.png
   :width: 80%
   :align: center
   :alt: Answer keys summary page for the math quiz

The companion ``exam_version_keys.csv`` can be passed directly to
``pyaota grade`` via ``-k``.

----

Tips
----

* Use ``--seed`` to make builds reproducible: the same seed always produces the
  same version ordering and question selection.
* Increase ``--num-exams`` (``-n``) to generate as many unique versions as
  needed for a large class.
* Add ``--rasterize`` if your printer struggles with the TikZ-heavy answer sheet.
* Add ``--odd-page-answersheet`` for double-sided printing so the answer sheet
  always falls on the right-hand (odd) page.
* Use ``--font-size 10pt`` or ``11pt`` to fit more questions per page.
