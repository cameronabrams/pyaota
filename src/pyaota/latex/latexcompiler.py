# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
LaTeX compilation functions for pyaota
"""
import logging

from pathlib import Path

from ..util.command import Command
from ..util.collectors import FileCollector
from ..generator.document import Document

logger = logging.getLogger(__name__)

class LatexCompiler:
    def __init__(self, build_specs: dict):
        self.specs = build_specs
        self.pdflatex = self.specs['paths']['pdflatex']
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
        version: str | int = document.version

        serial = document.version
        self.working_job_name = self.job_name
        self.working_job_name = self.job_name + f'-{serial}'
        document.write_source(local_output_name=self.working_job_name)
        self.FC.append(f'{self.working_job_name}.tex')
        output_option = ''
        if self.build_dir != '.':
            output_option = f'-output-directory={self.build_dir}'
        build_path = Path.cwd() / self.build_dir
        if not build_path.exists():
            build_path.mkdir(parents=True, exist_ok=True)
        
        repeated_command = (f'{self.pdflatex} -interaction=nonstopmode -file-line-error '
                                f'-jobname={self.working_job_name} {output_option} {self.working_job_name}.tex')
        commands.append(Command(repeated_command, ignore_codes=[1]))

        self.FC.append(f'{self.build_dir}/{self.working_job_name}.aux')
        self.FC.append(f'{self.build_dir}/{self.working_job_name}.log')
        self.FC.append(f'{self.build_dir}/{self.working_job_name}.out')
        commands.append(Command(repeated_command, ignore_codes=[1]))
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
        for c in commands:
            logger.debug(f'Running command: {c.c}')
            out, err = c.run()
            logger.debug(f'Command output:')
            logger.debug('='*80)
            logger.debug(out)
            logger.debug('='*80)
            logger.debug(f'Command error:')
            logger.debug('='*80)
            logger.debug(err)
            logger.debug('='*80)
        if cleanup:
            logger.debug(f'Flushing {len(self.FC.data)} intermediate files.')
            self.FC.flush()
