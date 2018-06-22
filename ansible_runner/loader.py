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
import os
import json
import logging

from yaml import safe_load, YAMLError

from ansible_runner.exceptions import ConfigurationError, AnsibleRunnerException
from ansible_runner.utils import validate_ssh_key


class ArtifactLoader(object):
    '''
    Handles loading and caching file contents from disk

    This class will load the file contents and attempt to deserialize the
    contents as either JSON or YAML.  If the file contents cannot be
    deserialized, the contents will be returned to the caller as a string.

    The deserialized file contents are stored as a cached object in the
    instance to avoid any additional reads from disk for subsequent calls
    to load the same file.
    '''

    logger = logging.getLogger('ansible-runner')

    def __init__(self, base_path):
        self._cache = {}
        self.base_path = base_path

    def _load_json(self, contents):
        '''
        Attempts to deserialize the contents of a JSON object

        Args:
            contents (string): The contents to deserialize

        Returns:
            dict: If the contents are JSON serialized

            None: if the contents are not JSON serialized
        '''
        try:
            return json.loads(contents)
        except ValueError:
            pass

    def _load_yaml(self, contents):
        '''
        Attempts to deserialize the contents of a YAML object

        Args:
            contents (string): The contents to deserialize

        Retunrs:
            dict: If the contents are YAML serialized

            None: if the contents are not YAML serialized
        '''
        try:
            return safe_load(contents)
        except YAMLError as exc:
            self.logger.exception(exc)
            pass

    def get_contents(self, path):
        '''
        Loads the contents of the file specified by path

        Args:
            path (string): The relative or absolute path to the file to
                be loaded.  If the path is relative, then it is combined
                with the base_path to generate a full path string

        Returns:
            string: The contents of the file as a string

        Raises:
            ConfigurationError: If the file cannot be loaded
        '''
        try:
            if not os.path.exists(path):
                raise ConfigurationError('specified path does not exist %s' % path)

            with open(path) as f:
                data = f.read()

            return data

        except (IOError, OSError) as exc:
            self.logger.exception(exc)
            raise ConfigurationError('error trying to load file contents: %s' % exc)

    def abspath(self, path):
        '''
        Transform the path to an absolute path

        Args:
            path (string): The path to transform to an absolute path

        Returns:
            string: The absolue path to the file
        '''
        if not path.startswith(os.path.sep) or path.startswith('~'):
            path = os.path.expanduser(os.path.join(self.base_path, path))
        return path

    def _load_file_data(self, path, encoding='utf-8'):
        '''
        Load file contents from cache or disk.

        Args:
            path (string): The full or relative path to the file to be loaded

            encoding (string): The file contents text encoding
        Returns:
            contents: The file contents
            parsed_data: The file encoded data

        Raises:
            ConfigurationError:
        '''

        try:
            self.logger.debug('cache miss, attempting to load file from disk: %s' % path)
            contents = self.get_contents(path)
            parsed_data = contents.encode(encoding)
        except ConfigurationError as exc:
            self.logger.exception(exc)
            raise
        except UnicodeEncodeError as exc:
            self.logger.exception(exc)
            raise ConfigurationError('unable to encode file contents')
        return contents, parsed_data

    def load_key(self, path, encoding='utf-8'):
        '''
        Load the key specified by path

        This method will first try to load the key contents from cache and
        if there is a cache miss, it will load the contents from disk

        Args:
            path (string): The full or relative path to the file to be loaded

            encoding (string): The file contents text encoding
        Returns:
            key_data: The validated key

        Raises:
            AnsibleRunnerException:
        '''
        path = self.abspath(path)
        self.logger.debug('file path is %s' % path)

        if path in self._cache:
            return self._cache[path]
        else:
            contents, _ = self._load_file_data(path, encoding) 
        try:
            validate_ssh_key(contents)
        except AnsibleRunnerException as exc:
            print(exc)
            self.logger.exception(exc)

        self._cache[path] = contents 
        return contents


    def load_file(self, path, objtype=None, encoding='utf-8'):
        '''
        Load the file specified by path

        This method will first try to load the file contents from cache and
        if there is a cache miss, it will load the contents from disk

        Args:
            path (string): The full or relative path to the file to be loaded

            encoding (string): The file contents text encoding

            objtype (object): The object type of the file contents.  This
                is used to type check the deserialized content against the
                contents loaded from disk.

        Returns:
            object: The deserialized file contents which could be either a
                string object or a dict object

        Raises:
            ConfigurationError:
        '''
        path = self.abspath(path)
        self.logger.debug('file path is %s' % path)

        if path in self._cache:
            return self._cache[path]
        else:
            contents, parsed_data = self._load_file_data(path, encoding) 
        for deserializer in (self._load_json, self._load_yaml):
            parsed_data = deserializer(contents)
            if parsed_data:
                break

        if objtype and not isinstance(parsed_data, objtype):
            self.logger.debug('specified file %s is not of type %s' % (path, objtype))
            raise ConfigurationError('invalid file serialization type for contents')

        self._cache[path] = parsed_data
        return parsed_data
