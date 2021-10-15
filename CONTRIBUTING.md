# Ansible Runner Contributing Guidelines

Hi there! We're excited to have you as a contributor.

If you have questions about this document or anything not covered here? Come chat with us `#ansible-awx` on irc.libera.chat

## Things to know prior to submitting code

- All code and doc submissions are done through pull requests against the `devel` branch.
- Take care to make sure no merge commits are in the submission, and use `git rebase` vs `git merge` for this reason.
- We ask all of our community members and contributors to adhere to the [Ansible code of conduct]. If you have questions, or need assistance, please reach out to our community team at [codeofconduct@ansible.com].

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


[Ansible code of conduct]: http://docs.ansible.com/ansible/latest/community/code_of_conduct.html
[codeofconduct@ansible.com]: mailto:codeofconduct@ansible.com
