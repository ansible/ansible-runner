from ansible_runner.__main__ import main

import os


def test_help():
    try:
        main([])
        assert False, 'Should raise SystemExit with return code 2'
    except SystemExit as exc:
        assert exc.code == 2, 'Should raise SystemExit with return code 2'

def test_role():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          'run',
          'hello'])


