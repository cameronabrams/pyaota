import logging
import os
import shutil
import stat
import sys
import tarfile
import logging

from collections import UserList
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

logger = logging.getLogger(__name__)

def on_rm_error(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)

class FileCollector(UserList):
    """
    A class for handling collections of files to be managed together 
    as Paths
    """
    def __init__(self, initial: list[str | Path] = None):
        data: list[Path] = [Path(x) for x in initial] if initial is not None else []
        super().__init__(data)

    def append(self, item: str | Path):
        """
        Appends a file path to the collection
        
        Parameters
        ----------
        item : str | Path
            the file path to append
        """
        p = Path(item)
        if p not in self.data:
            self.data.append(p) 

    def flush(self):
        """
        Deletes all files in the collection from disk
        """
        logger.debug(f'Flushing file collector: {len(self.data)} entries.')
        for f in self.data:
            if f.is_file():
                # logger.debug(f'Deleting file {f.as_posix()} exists? {f.exists()}')
                f.unlink()
                # logger.debug(f'  -> exists? {f.exists()}')
            elif f.is_dir():
                # logger.debug(f'Deleting directory {f.as_posix()} exists? {f.exists()}')
                shutil.rmtree(f, onerror=on_rm_error)
                # logger.debug(f'  -> exists? {f.exists()}')
            else:
                logger.debug(f'FileCollector.flush: path {f.as_posix()} does not exist.')
        self.clear()

    def get_filenames(self) -> list[str]:
        """
        Returns list of filenames in the collection as strings
        """
        return [x.as_posix() for x in self.data]

    def __str__(self):
        cwd = Path.cwd()
        return ' '.join([x.relative_to(cwd).as_posix() for x in self.data])

    def archive(self, basepath: Path, delete: bool = False):
        """
        Archives the files in the collection into a single compressed file. If OS is Windows, makes a zipfile; if Linux, makes a tarball of the files in the collection.
        
        Parameters
        ----------
        basepath : Path
            basename of the resulting tarball or zipfile

        delete : bool, optional
            if True, deletes the original files after archiving (default is False)
        """
        # check the OS type first
        arcname = ''
        if sys.platform.startswith('win'):
            # Windows: make a zipfile
            zippath = basepath.with_suffix('.zip')
            with ZipFile(zippath, 'w', ZIP_DEFLATED) as zf:
                for src in self.data:
                    if src.is_file():
                        zf.write(src, arcname=src.name)
                    else:
                        for p in src.rglob("*"):
                            logger.debug(f'adding {p} to zipfile')
                            if p.is_file():
                                zf.write(p, arcname=p.relative_to(basepath.parent))
            logger.debug(f'generated zipfile {zippath}')
            arcname = zippath
        else:
            tgzpath = basepath.with_suffix('.tgz')
            with tarfile.open(tgzpath, 'w:gz') as tf:
                for f in self.data:
                    tf.add(f, arcname=f.name)
            logger.debug(f'generated tarball {tgzpath}')
            arcname = tgzpath
        if delete:
            self.flush()
        return arcname
