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
from typing import List, Pattern, Optional, Dict, Union

import requests
from packaging import version

from .git import GithubApp
from .settings import Settings

logger: logging.Logger = logging.getLogger(__name__)

# x-ref: PEP 440
PRE_RELEASE_PATTERN: Pattern[str] = re.compile(r'(a|b|rc|dev)[0-9]+$')


class Index:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _filter_releases(self, releases: List[str]) -> List[str]:
        filtered_releases = []
        for release in releases:
            if PRE_RELEASE_PATTERN.search(release):
                continue
            try:
                filtered_releases.append(version.parse(release))
            except version.InvalidVersion:
                logger.warning(f'Ignoring {release} due to parsing error')
                pass

        filtered_releases = sorted(filtered_releases, reverse=True)
        return [f'{release}' for release in filtered_releases]

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

        return self._filter_releases([release
                                      for release in package["releases"].keys()
                                      if not any([r["yanked"]
                                                  for r in package["releases"][release]])])


class GitIndex:
    def __init__(self, settings: Settings, github_app: Optional[GithubApp]) -> None:
        self._settings = settings
        self._github_app = github_app

    def _filter_releases(self, releases: List[str], raw_version: bool = False) -> List[str]:
        filtered_releases: List[Union[version.Version, str]] = []
        for release in releases:
            if PRE_RELEASE_PATTERN.search(release):
                continue
            try:
                parsed_version = version.parse(release)
            except version.InvalidVersion:
                logger.warning(f'Ignoring {release} due to parsing error')
            else:
                if raw_version:
                    filtered_releases.append(release)
                else:
                    filtered_releases.append(parsed_version)

        filtered_releases = sorted(filtered_releases, reverse=True)
        return [f'{release}' for release in filtered_releases]

    def _build_headers(self, org: str, repo: str) -> Dict[str, str]:
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if self._github_app is not None:
            access_token = self._github_app.get_access_token(f'{org}/{repo}')
            if access_token is not None:
                headers |= {'Authorization': f'Bearer {access_token}'}
        else:
            headers |= {'Authorization': f'token {os.environ.get("GITHUB_TOKEN", "")}'}
        return headers

    def get_tags_for_repo(self, org: str, repo: str) -> List[str]:
        r = requests.get(f'https://api.github.com/repos/{org}/{repo}/tags',
                         headers=self._build_headers(org, repo))
        r.raise_for_status()
        data = r.json()

        if data is None:
            raise ValueError(f'No tags found for: {data}')

        return self._filter_releases([tag["name"] for tag in data])

    def get_releases_for_repo(self, org: str, repo: str) -> List[str]:
        r = requests.get(f'https://api.github.com/repos/{org}/{repo}/releases',
                         headers=self._build_headers(org, repo))
        r.raise_for_status()
        data = r.json()

        if data is None:
            raise ValueError(f'No releases found for: {data}')

        return self._filter_releases([release["tag_name"] for release in data], True)
