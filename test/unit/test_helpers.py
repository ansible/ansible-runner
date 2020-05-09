# -*- coding: utf-8 -*-
#
# Copyright (c) 2019 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
import pytest

from ansible_runner import helpers


def test_isvalidattrname():
    with pytest.raises(ValueError):
        helpers.isvalidattrname('import')

    with pytest.raises(ValueError):
        helpers.isvalidattrname('0test')

    helpers.isvalidattrname('test')


def test_to_list():
    assert helpers.to_list(None) == []
    assert helpers.to_list('test') == ['test']
    assert helpers.to_list(['test']) == ['test']
    assert helpers.to_list(('test',)) == ['test']
    assert helpers.to_list(set(['test'])) == ['test']
