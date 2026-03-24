import os
import sys
import importlib.metadata

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

project = 'pyaota'
release = importlib.metadata.version(project)
version = '.'.join(release.split('.')[:2])

# -- Project information

copyright = '2025-2026, Cameron F. Abrams'
author = 'Cameron F. Abrams <cfa22@drexel.edu>'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx_autodoc_typehints',
    'myst_parser',
    'sphinx_copybutton',
]

autosummary_generate = True

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

# Mock imports that may not be available or broken in the docs build environment
autodoc_mock_imports = [
    'tensorflow', 'keras',
    'cv2',
    'pandas',
    'pdf2image',
    'win32com', 'win32com.client',
]

# -- Options for HTML output

html_theme = 'furo'

html_theme_options = {
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/cameronabrams/pyaota",
            "html": """
    <svg role="img" width="24" height="24" viewBox="0 0 24 24"
         xmlns="http://www.w3.org/2000/svg" fill="currentColor">
        <title>GitHub</title>
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.54-1.38-1.33-1.75-1.33-1.75-1.09-.75.08-.74.08-.74 1.2.08 1.83 1.23 1.83 1.23 1.07 1.83 2.81 1.3 3.5.99.11-.77.42-1.3.76-1.6-2.67-.3-5.47-1.34-5.47-5.98 0-1.32.47-2.4 1.24-3.24-.12-.3-.54-1.51.12-3.14 0 0 1.01-.32 3.3 1.23a11.38 11.38 0 0 1 3 0c2.28-1.55 3.3-1.23 3.3-1.23.66 1.63.24 2.84.12 3.14.77.84 1.24 1.92 1.24 3.24 0 4.65-2.8 5.68-5.47 5.98.43.37.81 1.1.81 2.22v3.29c0 .32.22.69.82.58C20.56 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z"/>
    </svg>
""",
            "class": "github-icon",
        },
    ],
}

html_static_path = ['_static']

# -- Options for EPUB output
epub_show_urls = 'footnote'
