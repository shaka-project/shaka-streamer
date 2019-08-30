# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A module sending content in named pipes to /dev/null."""

import os
import shlex
import subprocess

from . import node_base

class DiscardNode(node_base.NodeBase):

  def __init__(self, named_pipes):
    node_base.NodeBase.__init__(self)
    self._named_pipes = named_pipes

  def start(self):
    # Tail allows reading from multiple sources simultaneously, so it can
    # concurrently read from all the pipes passed into named_pipes.
    cmd = 'tail -f %s >/dev/null' % ' '.join(
        map(shlex.quote, self._named_pipes))
    self._process = subprocess.Popen(cmd, shell=True)
