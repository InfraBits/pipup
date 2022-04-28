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
import base64
import logging
import os
import time
from pathlib import PosixPath
from typing import Optional, List, Tuple, Dict

import requests

logger: logging.Logger = logging.getLogger(__name__)


class Git:
    def __init__(self, repository: str, branch_name: str) -> None:
        self.repository = repository
        self._headers = {
            'Authorization': f'token {os.environ.get("GITHUB_TOKEN", "")}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self._branch_name = branch_name

    def get_default_branch(self) -> Tuple[str, str]:
        r = requests.get(f'https://api.github.com/repos/{self.repository}',
                         headers=self._headers)
        r.raise_for_status()
        data: Dict[str, Tuple[str, str]] = r.json()
        return data['default_branch']

    def get_head_ref(self) -> Tuple[Optional[str], Optional[str]]:
        r = requests.get('https://api.github.com/repos/'
                         f'{self.repository}/git/refs',
                         headers=self._headers)
        r.raise_for_status()

        default_branch = self.get_default_branch()
        for branch in r.json():
            if branch['ref'] == f'refs/heads/{default_branch}':
                return branch['ref'], branch['object']['sha']
        return None, None

    def create_branch(self, base_sha: str) -> None:
        r = requests.post('https://api.github.com/repos/'
                          f'{self.repository}/git/refs',
                          json={
                              'ref': f'refs/heads/{self._branch_name}',
                              'sha': base_sha,
                          },
                          headers=self._headers)
        r.raise_for_status()

    def get_file_sha(self, path: PosixPath) -> Optional[str]:
        r = requests.get('https://api.github.com/repos/'
                         f'{self.repository}/contents/{path}',
                         json={'branch': self._branch_name},
                         headers=self._headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: Dict[str, Optional[str]] = r.json()
        return data['sha']

    def update_branch_file(self,
                           path: PosixPath,
                           contents: str,
                           commit_summary: str,
                           commit_body: Optional[str]) -> str:
        r = requests.put('https://api.github.com/repos/'
                         f'{self.repository}/contents/{path}',
                         json={
                             'message': (f'{commit_summary}\n{commit_body}'
                                         if commit_body else commit_summary),
                             'branch': self._branch_name,
                             'content': base64.b64encode(contents.encode('utf-8')).decode('utf-8'),
                             'sha': self.get_file_sha(path),
                         },
                         headers=self._headers)
        r.raise_for_status()
        data: Dict[str, Dict[str, str]] = r.json()
        return data['commit']['sha']

    def create_pull_request(self, head_ref: str, summary: str, description: str) -> int:
        r = requests.post('https://api.github.com/repos/'
                          f'{self.repository}/pulls',
                          json={
                              'title': summary,
                              'body': description,
                              'head': self._branch_name,
                              'base': head_ref,
                          },
                          headers=self._headers)
        r.raise_for_status()
        data: Dict[str, int] = r.json()
        return data['number']

    def get_pull_request_actions(self, pull_request_id: int) -> Dict[str, str]:
        r = requests.get('https://api.github.com/repos/'
                         f'{self.repository}/actions/runs',
                         json={'branch': self._branch_name},
                         headers=self._headers)
        r.raise_for_status()
        return {
            action['name']: action['conclusion']
            for action in r.json()['workflow_runs']
            if action['conclusion']
            if action['event'] == 'pull_request'
            if any([pr['number'] == pull_request_id
                    for pr in action['pull_requests']])
        }

    def merge_pull_request(self, pull_request_id: int) -> None:
        r = requests.put(f'https://api.github.com/repos/'
                         f'{self.repository}/pulls/{pull_request_id}/merge',
                         headers=self._headers)
        r.raise_for_status()

    def create_commit_comment(self, sha: str, comment: str) -> None:
        r = requests.post(f'https://api.github.com/repos/'
                          f'{self.repository}/commits/{sha}/comments',
                          json={'body': comment},
                          headers=self._headers)
        r.raise_for_status()

    def delete_branch(self) -> None:
        r = requests.delete(f'https://api.github.com/repos/'
                            f'{self.repository}/git/refs/heads/{self._branch_name}',
                            headers=self._headers)
        r.raise_for_status()

    def wait_for_workflows(self, required_workflows: List[str], pull_request_id: int) -> bool:
        required_workflows = [required_workflow.lower()
                              for required_workflow in required_workflows]
        logger.info(f'Waiting for: {required_workflows}')

        while True:
            pull_request_actions = {
                k.lower(): v
                for k, v in self.get_pull_request_actions(pull_request_id).items()
            }
            logger.info(f'Found workflows: {pull_request_actions}')

            if all([
                workflow in pull_request_actions
                for workflow in required_workflows
            ]):
                logger.info('All required workflows have concluded')

                happy_bunny = True
                for required_workflow in required_workflows:
                    if pull_request_actions[required_workflow] != 'success':
                        logger.error(f'Workflow for {required_workflow} failed'
                                     f': {pull_request_actions[required_workflow]}')
                        happy_bunny = False
                return happy_bunny

            logger.info('Missing required workflows, waiting....')
            time.sleep(5)
