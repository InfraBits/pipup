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
from typing import List

import requests
from packaging import version

from .settings import Settings

logger: logging.Logger = logging.getLogger(__name__)


class Index:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_releases_for_package(self, name: str) -> List[str]:
        package = None
        for mirror in self._settings.mirrors:
            r = requests.get(mirror.format(name=name))
            if r.status_code == 404:
                continue
            r.raise_for_status()
            package = r.json()
            break

        if package is None:
            raise ValueError(f'No release found for: {name}')

        releases = sorted([f'{version.parse(rel)}'
                           for rel in package["releases"].keys()],
                          key=lambda x: version.parse(x),
                          reverse=True)

        return releases
