"""
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
"""

import logging
import subprocess
from pathlib import PosixPath
from typing import List

import requests
from packaging import version

from .models import LockFile, PythonVersionFile
from .settings import Settings
import xml.etree.ElementTree as ET

logger: logging.Logger = logging.getLogger(__name__)


class PythonVersion:
    def __init__(self, path: PosixPath, settings: Settings) -> None:
        self._path = path
        self._settings = settings

    def _has_py_version_pin(self):
        return self._get_py_version_path().exists()

    def _get_py_version_path(self):
        return (self._path / ".python-version").absolute()

    def _get_current_pin(self):
        with self._get_py_version_path().open("r") as fh:
            return fh.read().strip()

    def _get_latest_python_release(self):
        r = requests.get(
            "https://heroku-buildpack-python.s3.us-east-1.amazonaws.com", timeout=10
        )
        r.raise_for_status()

        potential_releases = set()
        for entry in ET.fromstring(r.text).findall(".//{*}Key"):
            package_name = PosixPath(entry.text).name
            if package_name.startswith("python-") and "-ubuntu-22.04-" in package_name:
                potential_releases.add(version.parse(package_name.split("-")[1]))

        if potential_releases:
            return f"{sorted(potential_releases, reverse=True)[0]}"
        return None

    def update(self) -> List[PythonVersionFile]:
        if self._has_py_version_pin():
            latest_release = self._get_latest_python_release()
            current_release = self._get_current_pin()

            if latest_release != current_release:
                return [
                    PythonVersionFile(
                        self._get_py_version_path().relative_to(self._path),
                        current_release,
                        latest_release,
                    )
                ]

        return []
