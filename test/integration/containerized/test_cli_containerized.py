# -*- coding: utf-8 -*-
import os

HERE = os.path.abspath(os.path.dirname(__file__))

def test_module_run(cli):
    cli(['-m', 'ping','--hosts', 'localhost', 'run', os.path.join(HERE, 'priv_data')])

def test_playbook_run(cli):
    cli(['run', os.path.join(HERE,'priv_data'), '-p', 'test-container.yml'])

