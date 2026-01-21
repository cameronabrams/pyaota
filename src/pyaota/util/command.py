# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
Simple command runner
"""
import subprocess
import logging

logger = logging.getLogger(__name__)

class Command:
    def __init__(self, command: str, ignore_codes: list[int] = [], **options):
        """
        Initializes the Command instance.
        
        Parameters
        ----------
        command : str
            the base command to run
        ignore_codes : list of int, optional
            list of return codes to ignore (default is empty list)
        options : dict
            command-line options as key-value pairs
        """
        self.command = command
        self.ignore_codes = ignore_codes
        self.options = options
        self.c = f'{self.command} ' + ' '.join([f'-{k} {v}' for k, v in self.options.items()])
        
    def run(self):
        """
        Runs the command and returns the output and error messages.
        """
        process = subprocess.Popen(self.c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = process.communicate()
        if process.returncode != 0 and not process.returncode in self.ignore_codes:
            raise subprocess.SubprocessError(f'Command "{self.c}" failed with returncode {process.returncode}')
        return out, err