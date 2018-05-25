Ansible Runner
==============

Ansible Runner is a tool and python library that helps when interfacing with Ansible from other systems whether through a container image interface, as a standalone tool, or imported into a python project.

# Basic Evaluation Usage

The base reference container image includes a demo playbook and inventory that uses a local connection to demonstrate basic functionality.

```bash
$ docker run -it --rm -e RUNNER_PLAYBOOK=test.yml ansible/ansible-runner:latest
```

The `ansible-runner` command can also directly run roles without the need for a
playbook.  The following example demonstrates how to invoke a role directly
using `ansible-runner`:

```bash
$ ansible-runner run ./demo -r testrole --roles-path ./demo/roles
```

The above example will run the role called `testrole` from the `demo` folder in
the `ansible-runner` project root directory.


# Understanding the Ansible Runner Directory Hierarchy Interface

Ansible Runner takes most of its inputs from a particular directory structure. Some inputs can also be given on the command line. Primarily the `ansible-runner` command line utility requires at least two parameters:

* A command, one of:
  * run - This launches the runner command in the foreground and runs to completion. runner will still write data into its `artifacts` directory
  * start - This launches the runner command in the background and writes a pid into the `artifacts` directory
  * stop - This will terminate a runner process that has been started in the background
  * is-alive - Checks the status of a background runner process
* A base directory which contains all of the metadata necessary to run

## Input Directory Structure
The directory structure provided as an input for Runner looks like this

```
.
├── artifacts
├── env
│   ├── envvars
│   ├── extravars
│   ├── passwords
│   ├── settings
│   └── ssh_key
├── inventory
│   └── hosts
└── project
    └── test.yml
```

* artifacts - This directory will be created if it doesn't exist and is used to hold the output of runs
* env - This directory holds critical metadata used during launch
  * envvars - A yaml file that contains environment variables (see [./demo/env/envvars](./demo/env/envvars))
  * extravars - A yaml file that contains extra vars that will be passed to the runner. These will be effectively passed as `-e` parameters to `ansible-playbook` meaning they will take precedence over any other variables defined elsewhere. (see [./demo/env/extravars](./demo/env/extravars))
  * passwords - A yaml file that contains password prompt patterns and the value to be emitted (the password itself). These are regular expression patterns that runner looks for when processing the output from `ansible-playbook`. If the pattern is matched then the corresponding password will be emitted. (see [./demo/env/passwords](./demo/env/passwords))
  * settings - A yaml file representing some runner runtime settings (see [./demo/env/settings](./demo/env/settings)). If not provided defaults will be used
    * idle_timeout - This is a value in seconds from which, if there is no output emitted from `ansible-playbook` the runner will terminate the process
    * job_timeout - If the `ansible-playbook` process runs for longer than this number of seconds then it will be automatically terminated
    * pexpect_timeout - This is the amount of time in seconds runner will examine output to wait for password prompts that need to be emitted
  * ssh_key - This contains the ssh private key that will be passed to `ssh-agent` as part of the `ansible-playbook` execution.
  * inventory - This directory works exactly like `ansible` itself and will be passed as the inventory argument. The behavior is for Ansible to recurse into this directory and evaluate all files and scripts to generate inventory content. If your needs are pretty simple then you can create a simple file in this directory that contains a list of hosts/groups. `Note: If the --hosts argument is given to ansible-runner it will override ansible-playbook and this directory will not be given`
  * project - This directory should contain your playbooks and roles and will be set as the `cwd` when `ansible-playbook` starts.


## Output Directory Structure

As Runner executes it will write data into an artifacts directory using an identifier that is generated at runtime (or can be provided if `ansible-runner` is supplied with the `-i, --ident` command line argument), here's an example of a run of the demo playbook


```
.
└── artifacts
    └── 2d6a3ae1-e5de-4d4e-8e9e-eb237494b592
        ├── daemon.log
        ├── job_events
        │   ├── 0242ac11-0003-deb5-53a0-000000000006-partial.json
        │   ├── 0242ac11-0003-deb5-53a0-000000000008-partial.json
        │   ├── 0242ac11-0003-deb5-53a0-00000000000d-partial.json
        │   ├── 33d9ee70-9e86-4023-ab83-ac4c776d503a-partial.json
        │   ├── 7cd6f879-9429-4e3c-ba9a-1df98cad83f6-partial.json
        │   ├── 811f7983-a5e8-4ca5-8406-d39ae1088c1d-partial.json
        │   └── d5ac258b-ec43-465c-bdc3-0ac273061ef9-partial.json
        ├── rc
        ├── status
        └── stdout
```

* daemon.log - This contains log messages and errors emitted by `ansible-runner` itself
* job_events - This represents the callback/event data emitted from each ansible task and ansible host task as a json data structure. For example, here's the final `playbook_on_stats` event:

```
{
  "uuid": "d5ac258b-ec43-465c-bdc3-0ac273061ef9",
  "created": "2018-03-01T18:22:47.937822",
  "pid": 148,
  "event_data": {
    "skipped": {
      
    },
    "ok": {
      "localhost": 2
    },
    "artifact_data": {
      
    },
    "changed": {
      
    },
    "pid": 148,
    "dark": {
      
    },
    "playbook_uuid": "811f7983-a5e8-4ca5-8406-d39ae1088c1d",
    "playbook": "test.yml",
    "failures": {
      
    },
    "processed": {
      "localhost": 1
    }
  },
  "event": "playbook_on_stats"
}
```
* rc - The shell return code for the `ansible-playbook` process
* status - A textual representation of the final status of the job (success, failure)
* stdout - The `ansible-playbook` raw stdout stripped of control characters.

# Ansible Runner as a Container Image

Runner's existing container image is meant to be used as a base or reference container image. It includes a simple playbook and inventory with extra vars that it forces to run under a local collection.

The container image itself exposes several directories as volumes and those can be used to replace the metadata contexts given to the execution of the runner.

## Building the base container image

Start by building the source distribution:

```bash
$ make dist
...
```

Then construct the container image:

```bash
$ make image
...
```

By default the image is named `ansible-runner` which can be overridden by setting `IMAGE_NAME`

# Ansible Runner as a Python Interface

```bash
$ pip install ansible-runner
```

The runner module exposes two interfaces:

* `ansible_runner.run()` - Invokes runner in the foreground and returns a Runner object that can be used
  to inspect the run
* `ansible_runner.run_async()` - Invokes runner in a thread and returns the thread object and Runner object as a tuple

Example:
```bash
>>> import ansible_runner
>>> r = ansible_runner.run(private_data_dir="/tmp/demo", playbook="test.yml")

PLAY [all] *********************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [debug] *******************************************************************
ok: [localhost] => {
    "msg": "Test!"
}

PLAY RECAP *********************************************************************
>>> r.status
'successful'
>>> r.rc
0
```

The Runner object that's returned has a few interfaces that are useful:

* `stdout`: Returns a file-handle to the stdout representing the Ansible run.
* `events`: A generator that will return all ansible job events in the order that they were emitted from Ansible
* `stats`: Returns the final high level stats from the Ansible run
* `host_events()`: Given a host name, this will return all task events executed on the host

## Building the source distribution

To generate a source `.whl` distribution:

```bash
$ make dist
...
```
