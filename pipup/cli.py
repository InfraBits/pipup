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

import base64
import logging
import sys
import uuid
from pathlib import PosixPath
from typing import List, Optional, Union

import click

from .poetry import Poetry
from .git import GithubApp, Git
from .models import Requirements, LockFile
from .settings import Settings
from .updater import Updater

logger: logging.Logger = logging.getLogger(__name__)


def _update(
    path: PosixPath, settings: Settings, github_app: Optional[GithubApp]
) -> List[Requirements]:
    updater = Updater(path, settings, github_app)

    logger.info("Resolving requirements")
    updater.resolve_requirements()

    logger.info("Updating requirements")
    updated_requirements = updater.update_requirements()

    if not any([requirements.have_updates() for requirements in updated_requirements]):
        logger.info("No updates required")
        return []

    logger.info("Saving updated requirements files")
    for requirements in updated_requirements:
        if requirements.have_updates():
            logger.info(f" - {requirements.file_path}")
            with (path / requirements.file_path).open("w") as fh:
                fh.write(requirements.render_contents())

    return updated_requirements


def _merge(
    settings: Settings,
    repository: str,
    updates: List[Union[Requirements, LockFile]],
    github_app: GithubApp,
) -> bool:
    branch_name = f"pipup-{uuid.uuid4()}"
    logger.info(f"Merging updated requirements files using {branch_name}")

    # Handle the merging logic as required
    git = Git(repository, branch_name, github_app)
    head_ref, head_sha = git.get_head_ref()
    if not head_ref or not head_sha:
        logger.error("Failed to get head ref")
        return False

    git.create_branch(head_sha)

    pull_request_summary = f"pipup ({sum([r.update_count() for r in updates])} changes)"
    pull_request_description = ""
    branch_sha = None
    for update in updates:
        if update.have_updates():
            commit_summary = update.update_summary()
            commit_description = update.update_detail()

            pull_request_description += f"{update.file_path}:\n"
            pull_request_description += f"{commit_description}\n"

            logger.info(f" - {update.file_path}")
            logger.info(f"  Using commit summary: {commit_summary}")
            logger.info(f"  Using commit description: {commit_description}")
            branch_sha = git.update_branch_file(
                update.file_path,
                update.render_contents(),
                commit_summary,
                commit_description,
            )

    if not branch_sha:
        logger.info("No branch changes found, skipping PR")
        git.delete_branch()
        return False

    logger.info(f"Creating pull request for {branch_name}")
    if pull_request_id := git.create_pull_request(
        head_ref, pull_request_summary, pull_request_description.strip()
    ):
        logger.info(f"Waiting for workflows to complete on {branch_name}")
        if git.wait_for_workflows(settings.workflows, pull_request_id):
            logger.info(f"Merging pull request {pull_request_id}")
            git.merge_pull_request(pull_request_id)
            return True
        else:
            logger.info(f"Closing failed pull request {pull_request_id}")
            try:
                git.create_commit_comment(
                    branch_sha,
                    f'Expected workflow ({", ".join(settings.workflows)}) failed',
                )
            except Exception as e:
                logger.exception("Failed to create commit comment", e)
            git.delete_branch()
    return False


def _create_new_tag(repository: str, github_app: GithubApp) -> bool:
    git = Git(repository, None, github_app)
    latest_tag = git.get_latest_release_tag()
    if not latest_tag.startswith("v") or "." not in latest_tag:
        logger.error(f"Unknown release format: {latest_tag}")
        return False

    parts = latest_tag.split(".")
    try:
        increment = int(parts[-1]) + 1
    except ValueError:
        logger.error(f"Could not convert last part to number: {parts}")
        return False

    _, head_ref = git.get_head_ref()
    new_tag = f'{".".join(parts[0:-1])}.{increment}'
    logger.info(f"Creating tag {latest_tag} -> {new_tag} ({head_ref})")
    git.create_tag(new_tag, head_ref)


@click.command()
@click.option("--debug", is_flag=True, help="Increase logging level to debug")
@click.option("--merge", is_flag=True, help="Merge changes into a GitHub repo")
@click.option("--repository", help="Name of the GitHub repo these files belong to")
@click.option("--github-app-id", type=int, help="GitHub app id")
@click.option("--github-app-key", type=str, help="GitHub app private key")
@click.option("--path", help="Path to update", type=PosixPath, default=PosixPath.cwd())
def cli(
    debug: bool,
    path: PosixPath,
    merge: bool,
    repository: str,
    github_app_id: Optional[int] = None,
    github_app_key: Optional[str] = None,
) -> None:
    """pipup - Simple requirements updater."""
    logging.basicConfig(
        stream=sys.stderr,
        level=(logging.DEBUG if debug else logging.INFO),
        format="%(asctime)-15s %(message)s",
    )

    if merge and not repository:
        click.echo("--merge requires --repository")
        return

    # Load the settings for our runtime
    settings = Settings.load(path)
    logger.info(f"Using settings: {settings}")

    # Setup a GithubApp if needed
    github_app: Optional[GithubApp] = None
    if github_app_id and github_app_key:
        github_app = GithubApp(
            github_app_id, base64.b64decode(github_app_key).decode("utf-8")
        )

    poetry = Poetry(path.absolute(), settings)

    updates: List[Union[Requirements, LockFile]] = []
    updates.extend(poetry.update())
    updates.extend(_update(path, settings, github_app))

    # Create a pull request if required & we have changes
    if github_app and merge and updates:
        if _merge(settings, repository, updates, github_app):
            if settings.create_new_tag:
                _create_new_tag(repository, github_app)


if __name__ == "__main__":
    cli()
