# pipup - Simple requirements updater

A few different tools exist today such as pyup, however they either require a 3rd party service, or are (semi) abandoned.

pipup aims to achieve the goal of automatically updating requirements.txt files, with merging based on passing CI.

## Example usage

`.pipup.yaml`
```yaml
requirements:
  - requirements.txt
  - requirements-dev.txt
  - requirements-prod.txt
workflows:
  - CI
mirrors:
  - https://pypi.org/pypi/{name}/json
```

_Note: Sane defaults are used without a config file_

`requirements.txt`
```text
pyre-check==0.9.6 # pipup:ignore
pylama==7.7.1 # pipup:version:>=7.7.0,<8.0.0
```

_Note: All dependencies are updated by default_

`.github/workflows/pipup.yml`
```yaml
name: Update dependencies using pipup
on: {schedule: [{cron: '13 6 * * *'}], push: {branches: [main]}}
permissions: {contents: read}
jobs: {pipup: {runs-on: ubuntu-20.04,
               steps: [{uses: InfraBits/pipup@v1.0.1,
                        with: {github-access-token: ${{ secrets.OVERLORD_PAT }}}}]}}
```

_Note: Change the schedule/branches to suit the local repository_
_Note: A personal access token is required as the provided access token cannot trigger PR checks :(_
