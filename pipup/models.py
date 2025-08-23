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
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import PosixPath
from typing import List, Optional, Tuple, Union, Dict
from urllib.parse import urlparse

from dparse import parse, filetypes, dependencies  # type: ignore
from packaging.specifiers import SpecifierSet

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class DependencyOptions:
    specifier: SpecifierSet
    ignore: Optional[bool]
    use_tags: Optional[bool]
    allow_pre_releases: Optional[bool]
    raw: Optional[str]

    @staticmethod
    def parse_options(text: Optional[str]) -> "DependencyOptions":
        specifier, ignore, use_tags, allow_pre_releases, raw = (
            SpecifierSet(),
            False,
            False,
            False,
            text,
        )

        if text:
            text_to_parse = text
            while "pipup:" in text_to_parse:
                text_to_parse = "pipup:".join(text_to_parse.split("pipup:")[1:])
                option_to_parse = text_to_parse.split(" ")[0]

                if option_to_parse.startswith("version:"):
                    specifier = SpecifierSet(option_to_parse.split(":")[1])
                elif option_to_parse == "ignore":
                    ignore = True
                elif option_to_parse == "git:tags":
                    use_tags = True
                elif option_to_parse == "releases:pre":
                    allow_pre_releases = True

        return DependencyOptions(specifier, ignore, use_tags, allow_pre_releases, raw)


@dataclass
class RawDependency:
    line: str

    def export_requirements_txt(self) -> str:
        return self.line


@dataclass
class Dependency:
    name: str
    version_pin: Optional[str]
    extras: Optional[Tuple[str]]
    options: DependencyOptions

    @staticmethod
    def parse_dependency(dependency: dependencies.Dependency) -> "Dependency":
        return Dependency(
            dependency.name,
            f"{dependency.specs}".lstrip("=") if len(dependency.specs) > 0 else None,
            dependency.extras if len(dependency.extras) > 0 else None,
            DependencyOptions.parse_options(
                "#".join(dependency.line.split("#")[1:]).lstrip()
                if "#" in dependency.line
                else None
            ),
        )

    def export_requirements_txt(self) -> str:
        text = f"{self.name}"
        if self.extras:
            text += f"[{', '.join(self.extras)}]"
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
    dependencies: List[Union[RawDependency, Dependency]]
    updates: List[Update]

    @staticmethod
    def parse_requirements_txt(
        base_path: PosixPath, file_path: PosixPath
    ) -> "Requirements":
        dependencies: List[Union[RawDependency, GitHubDependency, Dependency]] = []
        with file_path.open("r") as fh:
            # parse does not support all lines, specifically git sourced dependencies
            # thus explicitly parse each line, so we can maintain order...
            for line in fh.readlines():
                deps = parse(line, filetypes.requirements_txt).dependencies
                if deps:
                    dependencies.append(Dependency.parse_dependency(deps[0]))
                    continue
                if (
                    line.strip().startswith("git+https://github.com/")
                    or line.strip().startswith("git+ssh://git@github.com/")
                ) and "#egg=" in line.strip():
                    if dep := GitHubDependency.parse_line(line.strip()):
                        dependencies.append(dep)
                        continue
                dependencies.append(RawDependency(line.strip()))
        return Requirements(file_path.relative_to(base_path), dependencies, [])

    def have_updates(self) -> bool:
        return len([update for update in self.updates if update.pin_changed]) > 0

    def update_count(self) -> int:
        return len([update for update in self.updates if update.pin_changed])

    def update_summary(self) -> str:
        return f"pipup: {self.update_count()} dependencies updated in {self.file_path}"

    def update_detail(self) -> str:
        commit_body = ""
        for update in sorted(
            self.updates, key=lambda u: (u.name, u.new_pin, u.previous_pin)
        ):
            if update.pin_changed:
                commit_body += f"* {update.name}:"
                if update.previous_pin:
                    commit_body += f" {update.previous_pin}"
                commit_body += f" -> {update.new_pin}\n"
        return commit_body

    def export_requirements_txt(self) -> str:
        return "\n".join(
            [
                f"{dependency.export_requirements_txt()}"
                for dependency in self.dependencies
            ]
            + [""]
        )


@dataclass
class GitHubDependency(Dependency):
    git_schema: str
    github_org: str
    github_repo: str
    version_pin: Optional[str]

    @staticmethod
    def parse_line(line: str) -> Optional["GitHubDependency"]:
        o = urlparse(line.split(" ")[0])
        current_scheme = o.scheme
        current_url = o.path.split("@")[0] if "@" in o.path else o.path
        current_tag = o.path.split("@")[1] if "@" in o.path else None

        if not current_url.endswith(".git"):
            # Not sure how to handle this
            logger.error(f"Found github url not pointing to git repo? {o}")
            return None

        path_parts = current_url.lstrip("/").split("/")
        if len(path_parts) != 2:
            # Not sure how to handle this
            logger.error(f"Found github url not pointing to org/repo? {path_parts}")
            return None

        extra = " ".join(line.split(" ")[1:]) if " " in line else ""
        dep_line = o.fragment.replace("egg=", "")
        if current_tag:
            dep_line += f"=={current_tag}"
        if extra:
            dep_line += f" {extra}"

        logger.debug(f'Using "{dep_line}" for "{line}"')

        dependencies = parse(dep_line, filetypes.requirements_txt).dependencies
        if len(dependencies) == 0:
            return None
        dependency = parse(dep_line, filetypes.requirements_txt).dependencies[0]
        dependency.version_pin = current_tag

        return GitHubDependency(
            dependency.name,
            f"{dependency.specs}".lstrip("=") if len(dependency.specs) > 0 else None,
            dependency.extras if len(dependency.extras) > 0 else None,
            DependencyOptions.parse_options(
                "#".join(dependency.line.split("#")[1:]).lstrip()
                if "#" in dependency.line
                else None
            ),
            current_scheme,
            path_parts[0],
            ".".join(path_parts[1].split(".")[:-1]),  # Strip off .git,
        )

    def render_contents(self) -> str:
        text = f"{self.git_schema}://{'git@' if self.git_schema == 'git+ssh' else ''}"
        text += f"github.com/{self.github_org}/{self.github_repo}.git"
        if self.version_pin:
            text += f"@{self.version_pin}"
        text += f"#egg={self.name}"
        if self.options.raw:
            text += f" # {self.options.raw}"
        return text


@dataclass
class LockFile:
    file_path: PosixPath
    current_contents: str
    new_contents: str

    def _get_packages_from_contents(self, contents: str) -> Dict[str, str]:
        data = tomllib.loads(contents)
        print(data)
        return {}

    @cache
    def _calculate_changes(self):
        previous_packages = self._get_packages_from_contents(self.current_contents)
        new_packages = self._get_packages_from_contents(self.new_contents)

        changes = {}
        for package in set(previous_packages.keys()) | set(new_packages.keys()):
            previous_version = previous_packages.get(package)
            new_version = new_packages.get(package)
            if previous_version != new_version:
                changes[package] = (previous_version, new_version)
        return changes

    def update_count(self) -> int:
        return len(self._calculate_changes().keys())

    def update_summary(self) -> str:
        return f"pipup: {self.update_count()} dependencies updated in {self.file_path}"

    def update_detail(self) -> str:
        commit_body = ""
        for package, (old, new) in sorted(
            self._calculate_changes(), key=lambda i: i[0]
        ):
            commit_body += f"* {package}:"
            if old:
                commit_body += f" {old}"
            commit_body += f" -> {new}\n"
        return commit_body

    def render_contents(self) -> str:
        return self.new_contents
