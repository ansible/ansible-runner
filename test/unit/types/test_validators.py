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

from ansible_runner.types.validators import ChoiceValidator
from ansible_runner.types.validators import RangeValidator
from ansible_runner.types.validators import PortValidator


def test_choice_validator_pass():
    v = ChoiceValidator(choices=['one', 'two', 'three'])
    v('one')
    v('two')
    v('three')


def test_choice_validator_fail():
    v = ChoiceValidator(choices=['one', 'two', 'three'])
    with pytest.raises(AttributeError):
        v('four')


def test_range_validator_pass():
    v = RangeValidator(1, 3)
    v(1)
    v(2)
    v(3)


def test_range_validator_fail():
    v = RangeValidator(1, 3)
    with pytest.raises(AttributeError):
        v(0)
    with pytest.raises(AttributeError):
        v(4)


def test_port_validator_pass():
    v = PortValidator()
    for i in range(1, 65535):
        v(i)


def test_port_validator_fail():
    v = PortValidator()
    with pytest.raises(AttributeError):
        v(0)
    with pytest.raises(AttributeError):
        v(65536)
