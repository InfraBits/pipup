'''
pipup - Simple requirements updater

MIT License

Copyright (c) 2022 Infra Bits

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
import logging
import subprocess
from pathlib import PosixPath
from typing import List

from .models import LockFile
from .settings import Settings

logger: logging.Logger = logging.getLogger(__name__)


class Poetry:
    def __init__(self, path: PosixPath, settings: Settings) -> None:
        self._path = path
        self._settings = settings

    def _is_poetry_project(self):
        return self._get_project_path().exists() and self._get_lock_path().exists()

    def _get_project_path(self):
        return (self._path / 'poetry.lock').absolute()

    def _get_lock_path(self):
        return (self._path / 'poetry.lock').absolute()

    def _get_locks(self):
        with self._get_lock_path().open('r') as fh:
            return fh.read()

    def update(self) -> List[LockFile]:
        if self._is_poetry_project():
            current_locks = self._get_locks()
            subprocess.run([
                'poetry', 'lock', '--regenerate', '--no-interaction'
            ], check=True, cwd=self._path)
            new_locks = self._get_locks()

            if current_locks != new_locks:
                return [LockFile(self._get_lock_path(), current_locks, new_locks)]

        return []
