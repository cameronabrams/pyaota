# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
Simple command runner
"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

class Command:
    def __init__(self, command: str, ignore_codes: list[int] = [], env: dict | None = None, **options):
        """
        Initializes the Command instance.
        
        Parameters
        ----------
        command : str
            the base command to run
        ignore_codes : list of int, optional
            list of return codes to ignore (default is empty list)
        env : dict, optional
            environment variables to set for the command, on top of the current environment
        options : dict
            command-line options as key-value pairs
        """
        self.command = command
        self.ignore_codes = ignore_codes
        self.env = env
        self.options = options
        self.c = f'{self.command} ' + ' '.join([f'-{k} {v}' for k, v in self.options.items()])
        self.returncode: int | None = None
        
    def run(self):
        """
        Runs the command and returns the output and error messages.
        """
        env = {**os.environ, **self.env} if self.env else None
        process = subprocess.Popen(self.c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        out_bytes, err_bytes = process.communicate()
        out = out_bytes.decode("utf-8", errors="replace")
        err = err_bytes.decode("utf-8", errors="replace")
        self.returncode = process.returncode
        if process.returncode != 0 and not process.returncode in self.ignore_codes:
            raise subprocess.SubprocessError(f'Command "{self.c}" failed with returncode {process.returncode}')
        return out, err