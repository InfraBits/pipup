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
from pathlib import PosixPath
from typing import List, Sequence, Union

from .index import Index
from .models import Requirements, Update, Dependency, RawDependency
from .settings import Settings

logger: logging.Logger = logging.getLogger(__name__)


class Updater:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._requirements: List[Requirements] = []
        self._index = Index(settings)

    def resolve_requirements(self) -> List[Requirements]:
        for requirements_path in self._settings.requirements:
            requirements = PosixPath(requirements_path)
            if not requirements.is_file():
                logger.info(f'Skipping: {requirements}')
                continue

            logger.info(f'Discovered: {requirements}')
            self._requirements.append(
                Requirements.parse_requirements_txt(requirements)
            )
        return self._requirements

    def update_requirements(self) -> List[Requirements]:
        _requirements: List[Requirements] = []
        for requirements in self._requirements:
            dependencies: List[Union[RawDependency, Dependency]] = []
            updates: List[Update] = []
            for dependency in requirements.dependencies:
                # This is something we can't really handle,
                # but need to pass back for the export
                if isinstance(dependency, RawDependency):
                    logger.info(f'Ignoring due to parser: {dependency}')
                    dependencies.append(dependency)
                    continue

                releases = []
                if dependency.options.ignore:
                    logger.info(f'Ignoring due to inline config: {dependency.name}')
                elif '://' in dependency.name:
                    logger.info(f'Ignoring due to url: {dependency.name}')
                else:
                    releases = self._index.get_releases_for_package(dependency.name)

                if dependency.options.specifier:
                    releases = [
                        release
                        for release in releases
                        if dependency.options.specifier.contains(release)
                    ]

                logger.debug(f'[{dependency.name}] Found releases after filtering: {releases}')
                if releases:
                    logger.debug(f'[{dependency.name}] Found latest release: {releases[0]} ('
                                 f'{"not " if releases[0] == dependency.version_pin else ""}'
                                 'changed)')

                updates.append(
                    Update(dependency.name,
                           dependency.version_pin,
                           (
                               releases[0]
                               if len(releases) > 0 else
                               dependency.version_pin
                           ),
                           (
                               len(releases) > 0 and releases[0] != dependency.version_pin
                           ))
                )

                dependencies.append(
                    dependency
                    if not releases else
                    Dependency(dependency.name, releases[0], dependency.extras, dependency.options)
                )

            _requirements.append(
                Requirements(requirements.file_path, dependencies, updates)
            )

        self._requirements = _requirements
        return self._requirements
