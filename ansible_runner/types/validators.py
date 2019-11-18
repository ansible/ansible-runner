#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#


class TypeValidator(object):
    """Validates the value type is the desired type
    """

    def __init__(self, type):
        self.type = type

    def __call__(self, value):
        if value is not None and not isinstance(value, self.type):
            raise TypeError(
                "value must be {}, got {}".format(self.type, type(value))
            )


class RequiredValueValidator(object):
    """Checks that the value is set
    """

    def __call__(self, value):
        if value is None:
            raise ValueError("missing required value")


class ChoiceValidator(object):
    """Validates the provided value is one of a static
    list of values
    """

    def __init__(self, choices):
        self.choices = frozenset(choices)

    def __call__(self, value):
        if value is not None and value not in self.choices:
            msg = '{} is an invalid choice. Possible choices are: {}'
            raise AttributeError(msg.format(value, self.choices))


class RangeValidator(object):
    """Validates that an integer value is contained within a
    minimum and maximum value.
    """

    def __init__(self, minval, maxval):
        self.minval = minval
        self.maxval = maxval

    def __call__(self, value):
        if value is not None and not self.minval <= value <= self.maxval:
            raise AttributeError('invalid range')


class PortValidator(RangeValidator):
    """Validates an integer is contained within the valid list
    of TCP and/or UDP port numbers (1-65535)
    """

    def __init__(self):
        super(PortValidator, self).__init__(1, 65535)
