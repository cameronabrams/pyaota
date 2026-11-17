# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
Document build functions for pyaota
"""

import logging

from .yaml2tex import QUESTION_BOX_PAD_PT, QUESTION_BOX_RULE_PT, render_question, tex_escape

from ..latex.content import (
    HEADMATTER,
    DEFAULT_PAGESTYLES_TEMPLATE,
    BEGIN_DOCUMENT,
    END_DOCUMENT,
)

logger = logging.getLogger(__name__)

def single_page_overflow_message(version: str) -> str:
    return (f'pyaota: the questions of version {version} do not fit above the answer strip '
            f'(a question runs into the strip or onto a second page)')


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
            # header fields are plain text: escape &, %, #, _ etc.
            'INSTITUTION': tex_escape(self.institution or ''),
            'COURSE': tex_escape(self.course or ''),
            'TERM': tex_escape(self.term or ''),
            'DOCUMENTNAME': tex_escape(self.documentname or ''),
            'VERSION': self.version,
            'FONTSIZE': self.specs.get('fontsize', '12pt'),
            'QUESTIONSPACING': self.specs.get('questionspacing', '24pt'),
            'QUESTIONBOXES': (r'\questionboxestrue' if self.specs.get('questionboxes', False)
                              else ''),
            'QUESTIONBOXPAD': f'{QUESTION_BOX_PAD_PT}pt',
            'QUESTIONBOXRULE': f'{QUESTION_BOX_RULE_PT}pt',
        }
        self.extra_preamble = self.specs.get('extra_preamble', '')
        self.pagestyles = self.specs.get('pagestyles', DEFAULT_PAGESTYLES_TEMPLATE)
        logger.debug(f'Number of questions: {len(self.question_list)}')
        content = HEADMATTER
        if self.extra_preamble:
            content += '\n' + self.extra_preamble
        content += '\n\n' + self.pagestyles + '\n\n' + BEGIN_DOCUMENT + '\n\n'
        single_page = self.specs.get('singlepage', False)
        if single_page and self.answersheet_tex:
            # The answer strip is drawn first, on page 1, and the questions must
            # fit above it.  Count the pages actually shipped out: the page counter
            # alone also advances when the questions fit and only the space after
            # the last one spills over, onto a page 2 that is never output.  A
            # column multicols ships too tall (into the strip) without a second
            # page is caught from the log, by LatexCompiler's overfull-page check.
            content += (r'\newcount\pyaotapages'
                        r'\AddToHook{shipout/after}{\global\advance\pyaotapages 1 }'
                        r'\AddToHook{enddocument/afterlastpage}{\ifnum\pyaotapages>1 '
                        r'\GenericError{}{' + single_page_overflow_message('<<<VERSION>>>') + '}'
                        r'{Use fewer or shorter questions, a smaller --font-size, or the two-page '
                        r'layout.}{}\fi}' '\n')
            content += self.answersheet_tex.rstrip() + '\n'
        content += self.instructions + '\n\n'
        question_columns = int(self.specs.get('questioncolumns', 1))
        if question_columns > 1 and single_page:
            # the room left for the question columns, and the space each question
            # adds below its box, for packing the questions if they overflow
            content += (r'\par\typeout{pyaota-measure: room \the\dimexpr'
                        r'\ifdim\pagegoal=\maxdimen\textheight\else\pagegoal\fi'
                        r'-\pagetotal-\multicolsep\relax\space gap \the\dimexpr<<<QUESTIONSPACING>>>'
                        r'\ifquestionboxes\else+\medskipamount\fi+\lineskip\relax}' '\n')
        if question_columns > 1:
            sep = self.specs.get('questioncolumnsep', '2em')
            rule = '0.4pt' if self.specs.get('questioncolumnrule', False) else '0pt'
            content += (f'\\begingroup\\setlength{{\\columnsep}}{{{sep}}}'
                        f'\\setlength{{\\columnseprule}}{{{rule}}}\n'
                        f'\\begin{{multicols}}{{{question_columns}}}\\raggedcolumns\n\n')
        for q in self.question_list:
            logger.debug(f'Rendering question: {q["id"]} {q["type"]}')
            content += self.question_renderer(q).rstrip() + '\n\n'
        if question_columns > 1:
            content += '\\end{multicols}\\endgroup\n\n'
        if self.endmessage:
            content += self.endmessage.rstrip() + '\n\n'
        if self.answersheet_tex and not single_page:
            content += '% Answer Sheet\n\n'
            content += self.answersheet_tex.rstrip() + '\n\n'
        content += END_DOCUMENT +'\n'
        for key, value in self.substitutions.items():
            content = content.replace(f'<<<{key}>>>', value)
        super().__init__(content=content)
