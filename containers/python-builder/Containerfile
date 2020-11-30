# Copyright (c) 2019 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM docker.io/centos:8

RUN dnf update -y \
  && dnf install -y python3-pip python3-wheel \
  && dnf clean all \
  && rm -rf /var/cache/dnf

RUN pip3 install --no-cache-dir bindep

COPY scripts/assemble /usr/local/bin/assemble
COPY scripts/get-extras-packages /usr/local/bin/get-extras-packages
COPY scripts/install-from-bindep /output/install-from-bindep
