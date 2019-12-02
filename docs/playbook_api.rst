.. _playbook_api:

Using the Runner as a playbook and inventory API to Ansible
============================================================

**Ansible Runner** provides a modeling API for programmatically building
**Ansible** playbooks and inventory objects that can be directly consumed by
**Ansible Runner**.  This allows **Ansible Runner** to be easily embedded into
3rd party applications without having to explicitly write playbooks and
inventory structures upfront.

There are two modeling APIs currently available to be consumed by Python
developers.  The first one is the :class:`Playbook
<ansible_runner.playbook.Playbook>` object.  This object provides a
programmable model for creating **Ansible** playbooks.  The second one is the
:class:`Inventory <ansible_runner.inventory.Inventory>` object.  This object
provides a programmable model for creating a consumable **Ansible** inventory.

Typed API
---------

Both models drive from a base set of typed models that provide an explicitly
typed model with data and type validation.  The objects all extend from
:class:`Object <ansible_runner.types.objects.Object>` and incorporiate
:class:`Attribute <ansible_runnery.types.attrs.Attribute>` to enforce data
integrity.  

All objects built using this typed API provide a :meth:`serialize()
<ansible_runner.types.objects.Object.serialize>` and :meth:`deserialize()
<ansible_runner.types.objects.Object.deserialize>` method to transform the 
Python object to and from a JSON data structure.  The JSON data structure can 
be directly injected into the **Ansible Runner** Python interface for 
consumption. 


``Playbook``
------------

:class:`ansible_runner.playbook.Playbook`

Provides a strongly typed programmable model for reading existing **Ansible**
playbooks and/or writing properly formatted **Ansible** playbooks in JSON. The
:class:`Playbook <ansible_runner.playbook.Playbook>` class provides a set of
attributes that implement the cooresoding **Ansible** playbook directives. 


Usage Examples
~~~~~~~~~~~~~~

This section provides some common usage examples about how to implement the
:class:`Playbook <ansible_runner.playbook.Playbook>` object.

.. code-block:: python

    >>> from ansible_runner.playbook import Playbook
    >>> playbook = Playbook()
    >>> play = playbook.new()
    >>> play.gather_facts = False
    >>> play.connection = 'local'
    >>> play.hosts = 'localhost'
    >>> task = play.tasks.new(action='debug')
    >>> task.args['msg'] = 'Hello World!'
    >>> import json
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                }
            ],
            "hosts": "localhost"
        }
    ]

Adding a new task to an :class:`Playbook <ansible_runner.playbook.Playbook>`
object.

.. code-block:: python

    >>> new_task = play.tasks.new(action='command', freeform='ls -l')
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                },
                {
                    "command": "ls -1"
                }
            ],
            "hosts": "localhost"
        }
    ]

Task lists can also contain :class:`Block
<ansible_runner.playbook.tasks.Block>` items.  To create a new task block
simple omit the `action` keyword argument.

.. code-block:: python

    >>> block = play.tasks.new()
    >>> block.block.new(action='debug', args={'msg': 'task #1 in block'})
    {"debug": {"msg": "task #1 in block"}}
    >>> block.rescue.new(action='debug', args={'msg': 'task #1 in rescue'})
    {"debug": {"msg": "task #1 in rescue"}}
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                },
                {
                    "command": "ls -1"
                },
                {
                    "rescue": [
                        {
                            "debug": {
                                "msg": "task #1 in rescue"
                            }
                        }
                    ],
                    "block": [
                        {
                            "debug": {
                                "msg": "task #1 in block"
                            }
                        }
                    ]
                }
            ],
            "hosts": "localhost"
        }
    ]


Blocks in task lists can also be nested as deep as necessary with the
``block``, ``rescue`` and ``always`` attributes fully accessible.

.. code-block:: python

    >>> nested_block = play.tasks.new()
    >>> level2_block = nested_block.block.new()
    >>> level2_block.block.new(action='debug', args={'msg': 'task #1 in nested block'})
    {"debug": {"msg": "task #1 in nested block"}}
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                },
                {
                    "command": "ls -1"
                },
                {
                    "rescue": [
                        {
                            "debug": {
                                "msg": "task #1 in rescue"
                            }
                        }
                    ],
                    "block": [
                        {
                            "debug": {
                                "msg": "task #1 in block"
                            }
                        }
                    ]
                },
                {
                    "block": [
                        {
                            "block": [
                                {
                                    "debug": {
                                        "msg": "task #1 in nested block"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
            "hosts": "localhost"
        }
    ]

Since both ``Tasks`` and ``Blocks`` implement the Python ``MutableSequence``
interface, entries can be inserted, appended to, and deleted as necessary.

.. code-block:: python

    >>> from ansible_runner.playbook.tasks import Task
    >>> task = Task(action='debug', args={'msg': 'inserted task into play'})
    >>> playbook[0].tasks.insert(0, task)
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false, 
            "connection": "local", 
            "tasks": [
                {
                    "debug": {
                        "msg": "inserted task into play"
                    }
                }, 
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                }, 
                {
                    "command": "ls -1"
                }, 
                {
                    "rescue": [
                        {
                            "debug": {
                                "msg": "task #1 in rescue"
                            }
                        }
                    ], 
                    "block": [
                        {
                            "debug": {
                                "msg": "task #1 in block"
                            }
                        }
                    ]
                }, 
                {
                    "block": [
                        {
                            "block": [
                                {
                                    "debug": {
                                        "msg": "task #1 in nested block"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ], 
            "hosts": "localhost"
        }
    ]
    
    >>> del playbook[0].tasks[3]
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "inserted task into play"
                    }
                },
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                },
                {
                    "command": "ls -1"
                },
                {
                    "block": [
                        {
                            "block": [
                                {
                                    "debug": {
                                        "msg": "task #1 in nested block"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
            "hosts": "localhost"
        }
    ]

Additional :class:`Play <ansible_runner.playbook.plays.Play>` objects can be 
added to playbook for supporting multi-play playbooks.

.. code-block:: python

    >>> new_play = playbook.new()
    >>> new_play.connection = 'ssh'
    >>> new_play.roles.new(name='example.role')
    {"name": "example.role"}
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "gather_facts": false,
            "connection": "local",
            "tasks": [
                {
                    "debug": {
                        "msg": "inserted task into play"
                    }
                },
                {
                    "debug": {
                        "msg": "Hello World!"
                    }
                },
                {
                    "command": "ls -1"
                },
                {
                    "block": [
                        {
                            "block": [
                                {
                                    "debug": {
                                        "msg": "task #1 in nested block"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
            "hosts": "localhost"
        },
        {
            "connection": "ssh",
            "hosts": "all",
            "roles": [
                {
                    "name": "example.role"
                }
            ]
        }
    ]

Existing playbooks can also be laoded into a programmable model using the
:meth:`deserialize() <ansible_runner.playbook.Playbook.deserialize>` method.  This
method takes a native Python data structure and builds the object.  This means
that the playbook must initially be loaded and deserialized by an external
library. 

.. code-block:: python

    >>> from ansible_runner.playbook import Playbook
    >>> playbook = Playbook()
    >>> import yaml
    >>> data = yaml.safe_load(open('demo/project/test.yml'))
    >>> print(data)
    [{'tasks': [{'debug': 'msg="Test!"'}], 'hosts': 'all'}]
    >>> type(data)
    <type 'list'>
    >>> playbook.deserialize(data)
    >>> type(playbook)
    <class 'ansible_runner.playbook.Playbook'>
    >>> import json
    >>> print(json.dumps(playbook.serialize(), indent=4))
    [
        {
            "tasks": [
                {
                    "debug": "msg=\"Test!\""
                }
            ],
            "hosts": "all"
        }
    ]


``Inventory``
-------------

:class:`ansible_runner.inventory.Inventory`

Implements a programmable model for building supported inventories for use with
**Ansible Runner**.  The :class:`ansible_runner.inventory.Inventory` supports
creating hosts, groups (children) and vars can can be serialized to a JSON data
structure that can be directly consumable by **Ansible Runner**.

Usage Examples
~~~~~~~~~~~~~~

The following section provides a common usage example that demonstrates how to
implement the :class:`Inventory <ansible_runner.inventory.Inventory>` object.

Create a new instance of :class:`Inventory
<ansible_runner.inventory.Inventory>` and add a new host to the inventory with
well-known **Ansible** variables.

.. code-block:: python

    >>> from ansible_runner.inventory import Inventory
    >>> inventory = Inventory()
    >>> host = inventory.hosts.new('localhost')
    >>> host.ansible_host = '127.0.0.1'
    >>> host.ansible_connection = 'local'
    >>> import json
    >>> print(json.dumps(inventory.serialize(), indent=4))
    {
        "all": {
            "hosts": {
                "localhost": {
                    "ansible_connection": "local",
                    "ansible_host": "127.0.0.1"
                }
            }
        }
    }


Additional arbitrary key/value variables can be associated with the host entry
in the inventory.

.. code-block:: python

    >>> host['key1'] = 'value1'
    >>> inventory.hosts['localhost']['key2'] = 'value2'
    >>> print(json.dumps(inventory.serialize(), indent=4))
    {
        "all": {
            "hosts": {
                "localhost": {
                    "key2": "value2",
                    "key1": "value1",
                    "ansible_connection": "local",
                    "ansible_host": "127.0.0.1"
                }
            }
        }
    }

Groups (children) can be added to the inventory.  When adding a new child
object to the inventory, the name of the child group is a required positional
argument.

.. code-block:: python

    >>> child = inventory.children.new('local')
    >>> child.ansible_user = 'admin'
    >>> child.ansible_password = 'password'
    >>> child.ansible_become = True
    >>> print(json.dumps(inventory.serialize(), indent=4))
    {
        "all": {
            "hosts": {
                "localhost": {
                    "key2": "value2",
                    "key1": "value1",
                    "ansible_connection": "local",
                    "ansible_host": "127.0.0.1"
                }
            },
            "children": {
                "local": {
                    "ansible_become": true,
                    "ansible_ssh_user": "admin",
                    "ansible_password": "password",
                    "ansible_ssh_pass": "password",
                    "ansible_user": "admin"
                }
            }
        }
    }

Arbitrary variables can be assigned to the inventory object.

.. code-block:: python

    >>> inventory.vars['key1'] = 'value1'
    >>> inventory.vars['key2'] = 'value2'
    >>> print(json.dumps(inventory.serialize(), indent=4))
    {
        "all": {
            "hosts": {
                "localhost": {
                    "key2": "value2",
                    "key1": "value1",
                    "ansible_connection": "local",
                    "ansible_host": "127.0.0.1"
                }
            },
            "children": {
                "local": {
                    "ansible_become": true,
                    "ansible_ssh_user": "admin",
                    "ansible_password": "password",
                    "ansible_ssh_pass": "password",
                    "ansible_user": "admin"
                }
            },
            "vars": {
                "key2": "value2",
                "key1": "value1"
            }
        }
    }
