.. _changelog:

Changelog
=========

All notable changes to pyaota will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

[0.4.0] - 2026-03-24
--------------------

Added
~~~~~

* **Interactive grading** (``--interactive`` flag on ``grade``) -- when a QR
  code, student-ID field, or answer bubble cannot be read automatically, pyaota
  pauses and prompts the operator at the terminal to supply the missing value.
  For unanswered questions a matplotlib window displays the bubble row so the
  operator can confirm or override the detected answer.  See :doc:`grading`
  for full details.

[0.3.0] - 2026-02-27
--------------------

Added
~~~~~

* **Compact MCQ choice layout** -- choices are automatically arranged in two
  columns when all choice texts are short enough (``_choices_columns`` helper).
* **True/False question simplification** -- T/F questions no longer render a
  separate choices block; the stem is prefixed with bold ``True (T) / False (F)``.
* **T/F correct-answer highlighting** -- in ``compile-dump`` the correct answer
  for T/F questions is visually indicated with a filled circle (``\correctlabel``),
  consistent with MCQ behaviour.
* **Greedy topic redistribution** -- ``get_random_selection`` no longer errors
  when a topic has fewer questions than the uniform quota; available questions
  are redistributed across better-stocked topics so the total count is always met.
* ``--font-size {10pt,11pt,12pt}`` option on ``build`` and ``compile-dump``
  (default ``12pt``).
* ``--question-spacing <LENGTH>`` option on ``build`` and ``compile-dump``
  (default ``24pt``).
* ``--bubble-font-size <PT>`` option on ``build`` and ``make-answersheet``
  (default ``8.0``); uses an absolute ``\fontsize`` command so bubble text is
  unaffected by the document class font size.
* ``--odd-page-answersheet`` flag on ``build`` and ``make-answersheet``; inserts
  a blank filler page when needed so the answer sheet always lands on an
  odd-numbered (right-hand) page for double-sided printing.
* ``--rasterize`` flag on ``build`` and ``make-answersheet``; post-processes the
  compiled PDF by rasterizing it at 300 DPI (via ``pdf2image`` + Pillow) to
  improve compatibility with printer RIPs that struggle with complex TikZ paths.
* Full command line is now echoed at ``DEBUG`` level to the diagnostic log at
  startup.

Fixed
~~~~~

* Excess vertical space between a code-block stem and the choices list in MCQs
  (cancelled the implicit ``belowskip`` of the ``lstlisting`` environment with
  ``\vspace{-\medskipamount}``).
* Answer sheet page always renders at 12 pt regardless of the ``--font-size``
  setting, since the layout dimensions are absolute.

[0.2.0] - 2026-01-26
--------------------

Added
~~~~~

* serialization of answer sheet layouts to JSON

[0.1.0] - 2026-01-26
--------------------

* Initial release of pyaota

Breaking Changes Policy
-----------------------

pyaota follows semantic versioning:

* **MAJOR** version (X.0.0): Incompatible API changes
* **MINOR** version (0.X.0): New functionality, backwards-compatible
* **PATCH** version (0.0.X): Bug fixes, backwards-compatible

Deprecation Warnings
--------------------

No features are currently deprecated.

When features are deprecated, they will:

1. Remain functional in current MAJOR version
2. Issue ``DeprecationWarning`` when used
3. Include migration instructions in warning message
4. Be documented in this changelog
5. Be removed in next MAJOR version

Contributing to Changelog
--------------------------

When contributing changes:

1. Add entry under ``[Unreleased]`` section
2. Use appropriate subsection (Added/Changed/Deprecated/Removed/Fixed/Security)
3. Write concise, user-focused descriptions
4. Link to relevant issue/PR numbers
5. Maintainers will organize entries during release

Example entry::

   [Unreleased]
   ------------
   
   Added
   ~~~~~
   * New equestion type: OCR short answer
   * something else 

   Fixed
   ~~~~~
   * poorly formatted answer sheet resutls

See Also
--------

* `GitHub Contributing Guide <https://github.com/cameronabrams/pyaota/blob/main/CONTRIBUTING.md>`_ - How to contribute
* `GitHub Releases <https://github.com/cameronabrams/pyaota/releases>`_ - Release notes
* `GitHub Issues <https://github.com/cameronabrams/pyaota/issues>`_ - Bug reports and feature requests