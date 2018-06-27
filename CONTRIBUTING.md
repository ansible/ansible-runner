# Ansible Runner Contributing Guidelines

Hi there! We're excited to have you as a contributor.

If you have questions about this document or anything not covered here? Come chat with us `#ansible-awx` on irc.freenode.net

## Things to know prior to submitting code

- All code and doc submissions are done through pull requests against the `master` branch.
- Take care to make sure no merge commits are in the submission, and use `git rebase` vs `git merge` for this reason.
- We ask all of our community members and contributors to adhere to the [Ansible code of conduct](http://docs.ansible.com/ansible/latest/community/code_of_conduct.html). If you have questions, or need assistance, please reach out to our community team at [codeofconduct@ansible.com](mailto:codeofconduct@ansible.com)   

## Setting up your development environment

It's entirely possible to develop on **Ansible Runner** simply with

```bash
(host)$ python setup.py develop
```

Another (recommended) way is to use [Pipenv](https://docs.pipenv.org/), make sure you have it installed and then:

```bash
(host)$ pipenv install --dev
```

This will automatically setup the development environment under a virtualenv, which you can then switch to with:

```bash
(host)$ pipenv shell
```

## Linting and Unit Tests

`tox` is used to run `flake8` and unit tests on both Python 2 and 3. It uses pipenv to bootstrap these two environments.
