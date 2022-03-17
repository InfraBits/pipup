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
from dataclasses import dataclass
from pathlib import PosixPath
from typing import List, Optional

from dparse import parse, filetypes, dependencies
from packaging.specifiers import SpecifierSet

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class DependencyOptions:
    specifier: SpecifierSet
    ignore: Optional[bool]
    raw: Optional[str]

    @staticmethod
    def parse_options(text: Optional[str]) -> 'DependencyOptions':
        specifier, ignore, raw = SpecifierSet(), False, text

        if text:
            text_to_parse = text
            while 'pipup:' in text_to_parse:
                text_to_parse = 'pipup:'.join(text_to_parse.split('pipup:')[1:])
                option_to_parse = text_to_parse.split(' ')[0]

                if option_to_parse.startswith('version:'):
                    specifier = SpecifierSet(option_to_parse.split(':')[1])
                elif option_to_parse == 'ignore':
                    ignore = True

        return DependencyOptions(specifier, ignore, raw)


@dataclass
class Dependency:
    name: str
    version_pin: Optional[str]
    options: DependencyOptions

    @staticmethod
    def parse_dependency(dependency: dependencies.Dependency) -> 'Dependency':
        return Dependency(
            dependency.name,
            f'{dependency.specs}'.lstrip('=') if len(dependency.specs) > 0 else None,
            DependencyOptions.parse_options(
                '#'.join(dependency.line.split('#')[1:]).lstrip()
                if '#' in dependency.line else
                None
            ),
        )

    def export_requirements_txt(self) -> str:
        text = f"{self.name}"
        if self.version_pin:
            text += f"=={self.version_pin}"
        if self.options.raw:
            text += f" # {self.options.raw}"
        return text


@dataclass
class Update:
    name: str
    previous_pin: Optional[str]
    new_pin: Optional[str]
    pin_changed: bool


@dataclass
class Requirements:
    file_path: PosixPath
    dependencies: List[Dependency]
    updates: List[Update]

    @staticmethod
    def parse_requirements_txt(file_path: PosixPath) -> 'Requirements':
        dependencies = []
        with file_path.open('r') as fh:
            for dep in parse(fh.read(), filetypes.requirements_txt).dependencies:
                dependencies.append(Dependency.parse_dependency(dep))
        return Requirements(file_path, dependencies, [])

    def have_updates(self) -> bool:
        return len([update
                    for update in self.updates
                    if update.pin_changed]) > 0

    def update_summary(self) -> str:
        number_of_updates = len([update for update in self.updates if update.pin_changed])
        return f'pipup: {number_of_updates} dependencies updated in {self.file_path}'

    def update_detail(self) -> str:
        commit_body = ''
        for update in sorted(self.updates, key=lambda u: (u.name,
                                                          u.new_pin,
                                                          u.previous_pin)):
            if update.pin_changed:
                commit_body += f'* {update.name}:'
                if update.previous_pin:
                    commit_body += f' {update.previous_pin}'
                commit_body += f' -> {update.new_pin}\n'
        return commit_body

    def export_requirements_txt(self) -> str:
        return '\n'.join([
            f'{dependency.export_requirements_txt()}'
            for dependency in self.dependencies
        ] + [''])
