Installation
============

Requirements
------------

- Python 3.10 or later
- A working ``xelatex`` installation (e.g., TeX Live or MiKTeX)
- `Poppler <https://poppler.freedesktop.org/>`_ (required by ``pdf2image``;
  not installed by ``pip`` — see below)

Install from PyPI
-----------------

.. code-block:: bash

   pip install pyaota

Optional extras
---------------

- ``pip install 'pyaota[interactive]'`` -- matplotlib, needed for
  ``pyaota grade --interactive``
- ``pip install 'pyaota[test]'`` -- pytest, to run the test suite
- ``pip install 'pyaota[docs]'`` -- Sphinx and theme, to build this documentation

``pyaota return`` (emailing graded sheets) also needs Windows, Microsoft
Outlook and ``pip install pywin32``.

Install from source
-------------------

Clone the repository and install in editable mode:

.. code-block:: bash

   git clone https://github.com/cameronabrams/pyaota.git
   cd pyaota
   pip install -e .


Installing Poppler
------------------

Poppler is a system-level PDF library required by ``pdf2image``. It is not
installed automatically by ``pip``.

**Windows (conda):**

.. code-block:: bash

   conda install -c conda-forge poppler

**macOS:**

.. code-block:: bash

   brew install poppler

**Linux (Debian/Ubuntu):**

.. code-block:: bash

   sudo apt install poppler-utils

**Linux (openSUSE):**

.. code-block:: bash

   sudo zypper install poppler-tools

pyaota uses OpenCV's headless build (``opencv-python-headless``), so no display
libraries are needed.  If ``opencv-python`` is also installed in the same
environment the two conflict; uninstall ``opencv-python``.
