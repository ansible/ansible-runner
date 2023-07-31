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

from __future__ import annotations

import os
import json
import codecs

from typing import Any, Dict
from yaml import safe_load, YAMLError

from ansible_runner.exceptions import ConfigurationError
from ansible_runner.output import debug


class ArtifactLoader:
    '''
    Handles loading and caching file contents from disk

    This class will load the file contents and attempt to deserialize the
    contents as either JSON or YAML.  If the file contents cannot be
    deserialized, the contents will be returned to the caller as a string.

    The deserialized file contents are stored as a cached object in the
    instance to avoid any additional reads from disk for subsequent calls
    to load the same file.
    '''

    def __init__(self, base_path: str):
        self._cache: Dict[str, Any] = {}
        self.base_path = base_path

    def _load_json(self, contents: str) -> dict | None:
        '''
        Attempts to deserialize the contents of a JSON object

        :param str contents: The contents to deserialize.

        :return: A dict if the contents are JSON serialized,
            otherwise returns None.
        '''
        try:
            return json.loads(contents)
        except ValueError:
            return None

    def _load_yaml(self, contents: str) -> dict | None:
        '''
        Attempts to deserialize the contents of a YAML object.

        :param str contents: The contents to deserialize.

        :return: A dict if the contents are YAML serialized,
            otherwise returns None.
       '''
        try:
            return safe_load(contents)
        except YAMLError:
            return None

    def _get_contents(self, path: str) -> str:
        '''
        Loads the contents of the file specified by path

        :param str path: The relative or absolute path to the file to
            be loaded.  If the path is relative, then it is combined
            with the base_path to generate a full path string

        :return: The contents of the file as a string

        :raises: ConfigurationError if the file cannot be loaded.
        '''
        try:
            if not os.path.exists(path):
                raise ConfigurationError(f"specified path does not exist {path}")
            with codecs.open(path, encoding='utf-8') as f:
                data = f.read()

            return data

        except (IOError, OSError) as exc:
            raise ConfigurationError(f"error trying to load file contents: {exc}") from exc

    def abspath(self, path: str) -> str:
        '''
        Transform the path to an absolute path

        :param str path: The path to transform to an absolute path

        :return: The absolute path to the file.
        '''
        if not path.startswith(os.path.sep) or path.startswith('~'):
            path = os.path.expanduser(os.path.join(self.base_path, path))
        return path

    def isfile(self, path: str) -> bool:
        '''
        Check if the path is a file

        :param str path: The path to the file to check.  If the path is relative
            it will be exanded to an absolute path

        :return: True if path is a file, False otherwise.
        '''
        return os.path.isfile(self.abspath(path))

    def load_file(self, path: str, objtype: Any | None = None, encoding='utf-8') -> bytes | str | dict | None:
        '''
        Load the file specified by path

        This method will first try to load the file contents from cache and
        if there is a cache miss, it will load the contents from disk

        :param str path: The full or relative path to the file to be loaded.
        :param Any objtype: The object type of the file contents.  This
            is used to type check the deserialized content against the
            contents loaded from disk. Ignore serializing if objtype is str.
            Only Mapping or str types are supported.
        :param str encoding: The file contents text encoding.

        :return: The deserialized file contents which could be either a
            string object or a dict object

        :raises: ConfigurationError on error during file load or deserialization.
        '''
        parsed_data: bytes | str | dict | None
        path = self.abspath(path)
        debug(f"file path is {path}")

        if path in self._cache:
            return self._cache[path]

        try:
            debug(f"cache miss, attempting to load file from disk: {path}")
            contents = parsed_data = self._get_contents(path)
            if encoding:
                parsed_data = contents.encode(encoding)
        except ConfigurationError as exc:
            debug(str(exc))
            raise
        except UnicodeEncodeError as exc:
            raise ConfigurationError('unable to encode file contents') from exc

        if objtype is not str:
            for deserializer in (self._load_json, self._load_yaml):
                parsed_data = deserializer(contents)
                if parsed_data:
                    break

            if objtype and not isinstance(parsed_data, objtype):
                debug(f"specified file {path} is not of type {objtype}")
                raise ConfigurationError('invalid file serialization type for contents')

        self._cache[path] = parsed_data
        return parsed_data
