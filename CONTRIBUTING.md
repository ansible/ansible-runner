# Ansible Runner Contributing Guidelines

Hi there! We're excited to have you as a contributor.

If you have questions about this document or anything not covered here? Come chat with us `#ansible-awx` on irc.libera.chat

## Things to know prior to submitting code

- All code and doc submissions are done through pull requests against the `devel` branch.
- Take care to make sure no merge commits are in the submission, and use `git rebase` vs `git merge` for this reason.
- We ask all of our community members and contributors to adhere to the [Ansible code of conduct](http://docs.ansible.com/ansible/latest/community/code_of_conduct.html). If you have questions, or need assistance, please reach out to our community team at [codeofconduct@ansible.com](mailto:codeofconduct@ansible.com)

## Setting up your development environment

In this example we are using [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/), but any virtual environment will do.

```bash
(host)$ pip install virtualenvwrapper
(host)$ mkvirtualenv ansible-runner
(host)$ pip install -e .
```

When done making changes, run:

```
(host)$ deactivate
```

To reactivate the virtual environment:

```
(host)$ workon ansible-runner
```

## Linting and Unit Tests

`tox` is used to run linters (`flake8` and `yamllint`) and tests.

```
(host)$ pip install tox
(host)$ tox
```


## Backporting commits

For the purpose of these instructions, it is assumed a remote named `upstream` points to this repository and a remote named `origin` points at your fork. We want to backport commits from `devel` to the `release_2.0` branch.

```
origin	git@github.com:me/ansible-runner.git (fetch)
origin	git@github.com:me/ansible-runner.git (push)
upstream	https://github.com/ansible/ansible-runner.git (fetch)
upstream	https://github.com/ansible/ansible-runner.git (push)
```

### Using Cherry Picker 🍒⛏

1. Make sure cherry-picker is installed in the virtual environment.

        pip install cherry-picker

1. Then run `cherry_picker` with the revision that needs backporting.

    **Note:** It is possible to pass multiple branches to `cherry_picker`.

        cherry_picker --pr-remote origin [revision] release_2.0

    **Note:** `cherry_picker` does not currently support backporting merge commits. In this case, use a range of commits before the merge commit.

        cherry_picker --pr-remote origin [start revision]..[end revision] release_2.0


### Manually Backporting

1. Create a new branch from the target release branch.

    You may need to first fetch the upstream repository.

        git fetch upstream
        git checkout --no-track -b my-backport-branch upstream/release_2.0

1. Cherry pick the commit.

        git cherry-pick [revision]

    Or a range of commits

        git cherry-pick -x [start revision]..[end revision]

    Alternatively, squash all the commits in a merge commit into a singe commit for the backport.

        git cherry-pick -x [start revision]..[end revision] -m 1

1. Resolve any merge conflicts and push to your fork.

        git push -u origin my-backport-branch

1. Click the displayed URL to finish the backport process. Make sure the correct branch is selected for the pull request.
