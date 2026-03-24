YAML Question Schema
======================

This document describes the complete YAML schema for multiple‑choice questions.

Top-Level Structure
-------------------

A question file contains one top‑level key:

.. code-block:: yaml

    questions:
      - <question>
      - <question>
      ...

Question Structure
------------------

Each question is a mapping with the following required fields:

.. code-block:: yaml

    id: <string>
    topic: <string>
    points: <integer>
    type: mcq | tf
    stem: <list of stem blocks>
    choices: <list of 4 choices if mcq>
    correct: <a/b/c/d/true/false>
    explanation: <string>

``mcq`` questions have four choices (a, b, c, d), while ``tf`` questions have two choices (true, false).

Stem Blocks
-----------

Each question must contain **at least one** stem block of type ``text``.
A stem block has:

.. code-block:: yaml

    - type: text | code
      text: <string>

Rules:

* ``type: text`` blocks may contain inline code using double-backticks (``like this``).
* ``type: code`` blocks contain literal Python code.
* Printed output in code must not include quotes.
* Any literal newline in quoted YAML strings must appear as ``\n``.
* Multi-line code is preferably written using YAML block scalars (``|``).

Acceptable stem shapes include:

* ``text``
* ``text -> code``
* ``text -> code -> text``
* Multiple text blocks

Not allowed:

* A stem consisting only of ``code`` blocks.

Choices
-------

There must be exactly **four** choices, each with:

.. code-block:: yaml

    - key: a | b | c | d
      type: text | code
      text: <string>

Use ``type: code`` when the choice represents code or a Python literal, e.g.:

* ``x = 2 + 3``
* ``7``
* ``"hello"``
* ``x`` (identifier)
* ``n % 10``

Use ``type: text`` for prose answers.

Correct Answer and Explanation
------------------------------

* ``correct`` must match one of: ``a``, ``b``, ``c``, ``d``, or ``true``, ``false`` for a true-false.
* ``explanation`` is required and may contain inline code markup (``like this``).

Output Formatting Rules
-----------------------

* ``print("hello")`` → output is written as ``hello`` (no quotes).
* Expression values show quotes *only* when the Python literal includes them.
* Inline code only allowed in ``text`` blocks, never in ``code`` blocks.

Newline Rules
-------------

Inside quoted YAML scalars:

* Literal newlines **must** be written as ``\n``.
* Use block scalars (``|``) for multi-line code when possible.

Summary of Constraints
----------------------

1. Every question has at least one ``type: text`` stem block.
2. Code-only stems are forbidden.
3. Choices must use correct type (``text`` vs ``code``).
4. Inline code only in text blocks using double-backticks.
5. Exactly four choices per question.
6. Explanation required.
7. Printed output must never include quotes.

