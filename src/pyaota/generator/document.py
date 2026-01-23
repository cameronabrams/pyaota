# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
Document build functions for pyaota
"""

import logging

from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from .yaml2tex import render_question

from ..latex.content import (
    HEADMATTER,
    DEFAULT_PAGESTYLES_TEMPLATE,
    BEGIN_DOCUMENT,
    END_DOCUMENT,
)

logger = logging.getLogger(__name__)

class Document:
    def __init__(self, content: str = ""):
        self.content: str = content
    
    def write_source(self, local_output_name: str = 'document'):
        """
        Writes the LaTeX source to a local .tex file.
        
        Parameters
        ----------
        local_output_name : str
            the local output file name (without extension)
        """
        output_path = f'{local_output_name}.tex'
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.content)
        logger.info(f'Wrote LaTeX source to {output_path}')

class ExamDocument(Document):
    def __init__(self, document_specs: dict = {}):
        """
        Initializes the Document instance.
        
        Parameters
        ----------
        document_specs : dict
            document specifications
        """
        self.specs = document_specs
        self.institution = self.specs.get('institution', '')
        self.course = self.specs.get('course', '')
        self.term = self.specs.get('term', '')
        self.documentname = self.specs.get('examname', '')
        self.version = self.specs.get('version', '')
        self.question_renderer = self.specs.get('question_renderer', render_question)
        self.question_list = self.specs.get('question_list', [])
        self.answersheet_tex = self.specs.get('answersheet-tex', '')
        if not self.answersheet_tex:
            self.answersheet_tex = self.specs.get('answersheet_tex', '')
        self.instructions = self.specs.get('instructions', '')
        self.endmessage = self.specs.get('endmessage', '')
        self.substitutions: dict = {
            'INSTITUTION': self.institution,
            'COURSE': self.course,
            'TERM': self.term,
            'DOCUMENTNAME': self.documentname,
            'VERSION': self.version,
        }
        logger.debug(f'Number of questions: {len(self.question_list)}')
        content = HEADMATTER + '\n\n' + DEFAULT_PAGESTYLES_TEMPLATE + '\n\n' + BEGIN_DOCUMENT + '\n\n' + self.instructions + '\n\n'
        for q in self.question_list:
            logger.debug(f'Rendering question: {q["id"]} {q["type"]}')
            content += self.question_renderer(q).rstrip() + '\n\n'
        if self.endmessage:
            content += self.endmessage.rstrip() + '\n\n'
        if self.answersheet_tex:
            content += '% Answer Sheet\n\n'
            content += self.answersheet_tex.rstrip() + '\n\n'
        content += END_DOCUMENT +'\n'
        for key, value in self.substitutions.items():
            content = content.replace(f'<<<{key}>>>', value)
        super().__init__(content=content)
