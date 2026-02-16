Installation
============

Requirements
------------

- Python 3.10 or later
- A working ``pdflatex`` installation (e.g., TeX Live or MiKTeX)
- `Poppler <https://poppler.freedesktop.org/>`_ (for ``pdf2image``)

Install from source
-------------------

Clone the repository and install in editable mode:

.. code-block:: bash

   git clone https://github.com/cameronabrams/pyaota.git
   cd pyaota
   pip install -e .

Optional dependencies
---------------------

To install documentation build tools:

.. code-block:: bash

   pip install -e ".[docs]"

To install development tools (pytest, ruff, black):

.. code-block:: bash

   pip install -e ".[dev]"
