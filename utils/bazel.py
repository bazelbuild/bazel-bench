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
"""Handles Bazel invocations and measures their time/memory consumption."""
import subprocess
import os
import time
import psutil
import datetime
import utils.logger as logger


class Bazel(object):
  """Class to handle Bazel invocations.

  Allows to measure resource consumption of each command.

  Attributes:
    bazel_binary_path: A string specifying the path to the bazel binary to be
      invoked.
    bazelrc: A string specifying the argument to the bazelrc flag. Uses
      /dev/null if not set explicitly.
  """

  def __init__(self, bazel_binary_path, bazelrc):
    self._bazel_binary_path = str(bazel_binary_path)
    self._bazelrc_flag = '--bazelrc=%s' % (bazelrc or '/dev/null')
    self._pid = None

  def command(self, command_name, args=None, collect_memory=False):
    """Invokes a command with a bazel binary.

    Args:
      command_name: A string specifying the bazel command to invoke.
      args: An optional list of strings representing additional arguments to the
        bazel command.
      collect_memory: A boolean specifying whether to collect memory information
        for this command. Note that this retrieves the heap size from bazel a
        number of times to get stable data.

    Returns:
      A dict containing collected metrics (wall, cpu, system times and
      optionally memory), the exit_status of the Bazel invocation, and the
      start datetime (in UTC).
      Returns None instead if the command equals 'shutdown'.
    """
    args = args or []
    logger.log('Executing Bazel command: bazel %s %s' %
               (command_name, ' '.join(args)))

    result = dict()
    result['started_at'] = datetime.datetime.utcnow()

    before_times = self._get_times()
    dev_null = open(os.devnull, 'w')
    exit_status = 0

    try:
      subprocess.check_call(
        [self._bazel_binary_path, self._bazelrc_flag, command_name] + args,
        stdout=dev_null,
        stderr=dev_null
      )
    except subprocess.CalledProcessError as e:
      exit_status = e.returncode
      logger.log_error('Bazel command failed with exit code %s' % e.returncode)

    if command_name == 'shutdown':
      return None
    after_times = self._get_times()

    for kind in ['wall', 'cpu', 'system']:
      result[kind] = after_times[kind] - before_times[kind]
    result['exit_status'] = exit_status

    if collect_memory:
      # We do a number of runs here to reduce the noise in the data.
      result['memory'] = min([self._get_heap_size() for _ in range(5)])

    return result

  def _get_pid(self):
    """Returns the pid of the server.

    Has the side effect of starting the server if none is running. Caches the
    result.
    """
    if not self._pid:
      self._pid = (int)(
          subprocess.check_output([
              self._bazel_binary_path, self._bazelrc_flag, 'info', 'server_pid'
          ]))
    return self._pid

  def _get_times(self):
    """Retrieves and returns the used times."""
    # TODO(twerth): Getting the pid have the side effect of starting up the
    # Bazel server. There are benchmarks where we don't want this, so we
    # probably should make it configurable.
    process_data = psutil.Process(pid=self._get_pid())
    cpu_times = process_data.cpu_times()
    return {
        'wall': time.time(),
        'cpu': cpu_times.user,
        'system': cpu_times.system,
    }

  def _get_heap_size(self):
    """Retrieves and returns the used heap size."""
    return (int)(
        subprocess.check_output([
            self._bazel_binary_path, self._bazelrc_flag, 'info',
            'used-heap-size-after-gc'
        ])[:-3])
