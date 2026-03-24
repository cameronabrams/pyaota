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
