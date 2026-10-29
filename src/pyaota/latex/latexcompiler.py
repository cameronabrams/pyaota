# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
LaTeX compilation functions for pyaota
"""
import logging
import os
import re

from pathlib import Path

from ..util.command import Command
from ..util.collectors import FileCollector
from ..generator.document import Document

logger = logging.getLogger(__name__)


class LatexBuildError(RuntimeError):
    """The LaTeX engine reported errors, or produced no PDF."""


def latex_log_errors(log_path: Path, max_errors: int = 10) -> list[str]:
    """
    Return the error messages in a LaTeX log: lines starting with ``!`` and, since
    pyaota compiles with ``-file-line-error``, lines of the form ``file:line: message``.
    """
    if not log_path.exists():
        return []
    errors = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("!") or re.match(r"^[^\s:]+\.\w+:\d+: ", line):
            errors.append(line.strip())
            if len(errors) >= max_errors:
                break
    return errors


class LatexCompiler:
    def __init__(self, build_specs: dict):
        self.specs = build_specs
        self.latex_engine = self.specs['paths'].get('latex-engine', 'xelatex')
        self.build_dir: str = self.specs.get('paths', {}).get('build-dir', '.')
        self.job_name = self.specs.get('job-name', 'document')
        self.working_job_name = self.job_name
        self.FC = FileCollector()

    def _build_commands(self, document: Document = None):
        """
        Builds the list of commands needed to compile the document.
        
        Parameters
        ----------
        document : **Document**, optional
            the **Document** instance to compile (default is None)
            
        Returns
        -------
        list of Command
            list of **Command** instances to run for compilation
        """
        commands = []
        if not document:
            return commands
        # only exam documents carry a version; it suffixes the job name
        serial = getattr(document, 'version', None)
        self.working_job_name = self.job_name + (f'-{serial}' if serial else '')
        # The .tex goes in build_dir with the PDF: exam sources carry the answer
        # key, so they must not be left in the current directory.
        tex_stem = Path(self.build_dir) / self.working_job_name
        document.write_source(local_output_name=str(tex_stem))
        self.FC.append(f'{tex_stem}.tex')
        output_option = ''
        if self.build_dir != '.':
            output_option = f'-output-directory={self.build_dir}'
        build_path = Path.cwd() / self.build_dir
        if not build_path.exists():
            build_path.mkdir(parents=True, exist_ok=True)
        
        repeated_command = (f'{self.latex_engine} -interaction=nonstopmode -file-line-error '
                                f'-jobname={self.working_job_name} {output_option} {tex_stem}.tex')
        # TeX resolves \input and \includegraphics against the cwd, not the
        # .tex file's folder, and QR images are in build_dir. MiKTeX searches the
        # output directory for inputs; TeX Live does not, so add build_dir to
        # TEXINPUTS (the trailing separator keeps the default search path).
        # max_print_line keeps TeX Live from wrapping log lines at 79 characters,
        # so latex_log_errors reports whole messages
        env = {'TEXINPUTS': str(build_path) + os.pathsep + os.environ.get('TEXINPUTS', ''),
               'max_print_line': '10000'}
        commands.append(Command(repeated_command, ignore_codes=[1], env=env))

        self.FC.append(f'{self.build_dir}/{self.working_job_name}.aux')
        self.FC.append(f'{self.build_dir}/{self.working_job_name}.log')
        self.FC.append(f'{self.build_dir}/{self.working_job_name}.out')
        commands.append(Command(repeated_command, ignore_codes=[1], env=env))
        return commands

    def build_document(self, document: Document = None, cleanup: bool = False):
        """
        Builds the specified document by running the necessary commands.
        
        Parameters
        ----------
        document : **Document**, optional
            the **Document** instance to compile (default is None)
        cleanup : bool, optional
            if True, deletes intermediate files after build (default is False)
            """
        commands = self._build_commands(document)
        if not commands:
            return
        for c in commands:
            logger.debug(f'Running command: {c.c}')
            out, err = c.run()
            logger.debug('Command output:')
            logger.debug('='*80)
            logger.debug(out)
            logger.debug('='*80)
            logger.debug('Command error:')
            logger.debug('='*80)
            logger.debug(err)
            logger.debug('='*80)
        # Errors on earlier passes are expected (unresolved references); the final
        # pass must be clean, or the PDF cannot be trusted.
        pdf_path = Path(self.build_dir) / f'{self.working_job_name}.pdf'
        log_path = Path(self.build_dir) / f'{self.working_job_name}.log'
        if commands[-1].returncode != 0 or not pdf_path.exists():
            errors = latex_log_errors(log_path)
            detail = '\n  '.join(errors) if errors else '(no error lines found in the log)'
            raise LatexBuildError(
                f'{self.latex_engine} failed building {pdf_path} '
                f'(exit code {commands[-1].returncode}); see {log_path}:\n  {detail}'
            )
        if cleanup:
            logger.debug(f'Flushing {len(self.FC.data)} intermediate files.')
            self.FC.flush()
