YAML Question Schema
======================

This document describes the YAML schema for question banks: what pyaota reads
and checks, followed by recommended authoring conventions.

Top-Level Structure
-------------------

A question bank is a YAML file with a ``questions`` list and an optional
``topics`` list:

.. code-block:: yaml

    topics:            # optional; topics are also collected from the questions
      - Arithmetic
      - Fractions
    questions:
      - <question>
      - <question>
      ...

Several banks can be passed to one command (``-q a.yaml b.yaml``); their
questions are merged.

Question Structure
------------------

.. code-block:: yaml

    id: <integer or string>          # shown in compile-dump output
    type: mcq | tf                   # default: mcq
    topic: <string>                  # default: General
    points: <integer>                # default: 1
    difficulty: <integer 1-5>        # optional; used by --balance-difficulty
    stem: <list of stem blocks>
    choices: <list of choices>       # mcq only
    correct: <answer>                # or `answer:`; see below

The correct answer may be given as ``correct`` (preferred) or ``answer``;
if both are present, ``correct`` is used.

* **mcq:** ``correct`` is the key of one choice, matched without regard to case
  (``B`` selects the choice keyed ``b``).
* **tf:** ``correct`` is ``true`` or ``false``.  YAML booleans and the strings
  ``true``/``t``/``yes``/``y`` and ``false``/``f``/``no``/``n`` (any case) are
  accepted.

When a bank is loaded, pyaota checks every question and stops with a list of
problems (by question id) if any question has no answer, an answer that does
not match exactly one choice key, a true/false answer it cannot read, or a type
other than ``mcq`` or ``tf``.

Stem Blocks
-----------

The stem is a list of blocks rendered in order:

.. code-block:: yaml

    - type: text            # default
      text: <string>
    - type: code
      text: <string>        # rendered verbatim; any language
      style: <name>         # optional listings style (with --use-listings-from)
    - type: image
      src: <file name>      # looked up in an images/ folder next to the bank
      width: <pixels>       # optional; about 500 px is the full line width

Within ``text`` blocks (and choice texts):

* ``double backticks`` mark inline code, e.g. ````len(x)````.
* ``@@...@@`` marks inline math, passed to LaTeX as ``$...$``, e.g.
  ``@@x^2 + 1@@``.
* LaTeX special characters (``# $ % & _ { } ~ ^ \``) are escaped
  automatically, and Unicode superscript digits such as ``m²`` are typeset as
  superscripts.  Runs of four or more underscores become a fill-in blank.

Code is set verbatim by default.  Pass ``--use-listings-from <file.tex>`` (a
file defining an ``lstdefinestyle``) to ``build`` or ``compile-dump`` to set it
with the ``listings`` package instead; a block's or choice's ``style`` then
selects a style other than the default one.

Images referenced by ``image`` blocks must be in an ``images/`` folder next to
the bank file; they are copied into the output directory when the exam is
built.

Choices
-------

Multiple-choice questions list their choices:

.. code-block:: yaml

    choices:
      - key: a
        type: text | code   # default: text
        text: <string>
        style: <name>       # optional, code choices with listings only

The answer sheet has bubbles ``a`` to ``d``, so a multiple-choice question has
at most four choices, keyed ``a``, ``b``, ``c`` and ``d``.  With ``-sc``
(``--shuffle-choices``) the choices are shuffled and relabeled for each exam
version, and the answer key follows them.  Short choices are laid out
automatically in two columns, or all four on one row when they are very short.

True/false questions have no ``choices``; they are printed with a
``True (T) / False (F)`` prefix and answered in the first two bubbles.

Example
-------

.. code-block:: yaml

    topics:
      - Basics
    questions:
      - id: 1
        type: mcq
        topic: Basics
        difficulty: 2
        stem:
          - type: text
            text: "What does this print?"
          - type: code
            text: |
              console.log(typeof null);
        choices:
          - {key: a, type: code, text: "object"}
          - {key: b, type: code, text: "null"}
          - {key: c, type: code, text: "undefined"}
          - {key: d, type: code, text: "boolean"}
        correct: a
      - id: 2
        type: tf
        topic: Basics
        stem:
          - type: text
            text: "In JavaScript, an empty string is falsy."
        correct: true

Authoring Conventions
---------------------

These conventions are not checked by pyaota, but they keep banks consistent
and render well:

* Give every question at least one ``text`` stem block; avoid stems made only
  of code.
* Use ``type: code`` for choices that are code or literals (``x = 2 + 3``,
  ``"hello"``, ``n % 10``) and ``type: text`` for prose.
* When a choice shows printed output, write it as printed (``hello``, not
  ``"hello"``); show quotes only where the literal value includes them.
* Use inline code (double backticks) only in ``text`` blocks, never inside
  ``code`` blocks.
* Write multi-line code with YAML block scalars (``|``).  Inside quoted YAML
  strings, write newlines as ``\n``.
* An ``explanation`` field may be kept with each question for your own
  reference; pyaota does not print it.
