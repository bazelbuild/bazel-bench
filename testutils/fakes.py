# Copyright 2019 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Fakes for some functions/classes."""
import sys


def fake_log(text):
  """Fakes the log function. Prints to stderr."""
  sys.stderr.write(text)


def fake_exec_command(args, shell=False, fail_if_nonzero=True, cwd=None):
  """Fakes the _exec_command function."""
  fake_log(' '.join(args))


class FakeBazel(object):
  """Fake class for utils.Bazel"""

  def __init__(self, bazel_binary_path, bazelrc):
    # Do nothing
    return

  def command(self, command_name, args=None, collect_memory=False):
    """Fake method to verify that the command is executed."""
    args = args or []
    fake_log('Executing Bazel command: bazel %s %s' %
             (command_name, ' '.join(args)))
