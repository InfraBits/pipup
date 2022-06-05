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
import os
import re
from typing import List, Pattern

import requests
from packaging import version

from .settings import Settings

logger: logging.Logger = logging.getLogger(__name__)

# x-ref: PEP 440
PRE_RELEASE_PATTERN: Pattern[str] = re.compile(r'(a|b|rc|post|dev)[0-9]+$')


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

        releases = sorted([f'{version.parse(release)}'
                           for release in package["releases"].keys()
                           if PRE_RELEASE_PATTERN.search(release) is None
                           if not any([r["yanked"] for r in package["releases"][release]])],
                          key=lambda x: version.parse(x),
                          reverse=True)

        return releases


class GitIndex:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_tags_for_repo(self, org: str, repo: str) -> List[str]:
        r = requests.get(f'https://api.github.com/repos/{org}/{repo}/tags',
                         headers={
                             'Authorization': f'token {os.environ.get("GITHUB_TOKEN", "")}',
                             'Accept': 'application/vnd.github.v3+json'
                         })
        r.raise_for_status()
        data = r.json()

        if data is None:
            raise ValueError(f'No tags found for: {data}')

        return sorted([f'{version.parse(tag["name"])}'
                       for tag in data
                       if PRE_RELEASE_PATTERN.search(tag["name"]) is None],
                      key=lambda x: version.parse(x),
                      reverse=True)

    def get_releases_for_repo(self, org: str, repo: str) -> List[str]:
        r = requests.get(f'https://api.github.com/repos/{org}/{repo}/releases',
                         headers={
                             'Authorization': f'token {os.environ.get("GITHUB_TOKEN", "")}',
                             'Accept': 'application/vnd.github.v3+json'
                         })
        r.raise_for_status()
        data = r.json()

        if data is None:
            raise ValueError(f'No releases found for: {data}')

        return sorted([f'{version.parse(release["tag_name"])}'
                       for release in data
                       if PRE_RELEASE_PATTERN.search(release["tag_name"]) is None
                       if not release["draft"] and not release["prerelease"]],
                      key=lambda x: version.parse(x),
                      reverse=True)
