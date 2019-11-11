### Ansible Runner Test Data Directories

Subfolders in this directory should contain test cases in the form of
runner input directories.

If running from the top level of the ansible-runner directory, several
of these cases should be something which can be manually tested by the CLI
invocation.

```
ansible-runner run test/data/misc/ -p use_role.yml
```

The `misc` case is intended to hold playbooks and roles that do not require
any environment changes that would interfere with other playbooks.
