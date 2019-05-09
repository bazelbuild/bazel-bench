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
"""Tests for utils.bazel."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import collections
import mock
import unittest
import bazel


class BazelTest(unittest.TestCase):

  @mock.patch.object(bazel.subprocess, 'check_output', return_value='123\n')
  def test_get_pid(self, check_output_mock):
    b = bazel.Bazel('foo', None)
    self.assertEqual(123, b._get_pid())
    self.assertEqual(123, b._get_pid())
    # Verify that even that we called _get_pid twice, the we didn't spawn a
    # subprocess twice.
    self.assertEqual(1, check_output_mock.call_count)

  @mock.patch.object(bazel.subprocess, 'check_output', return_value='280MB\n')
  def test_get_heap_size(self, _):
    b = bazel.Bazel('foo', None)
    self.assertEqual(280, b._get_heap_size())

  @mock.patch.object(bazel.Bazel, '_get_pid', return_value=123)
  @mock.patch.object(bazel.time, 'time', return_value=98.76)
  @mock.patch.object(bazel.psutil, 'Process')
  def test_get_times(self, process_mock, unused_time_mock, unused_get_pid_mock):
    cpu_times = collections.namedtuple('cpu_times', 'user system')
    cpu_times_mock = process_mock.return_value
    cpu_times_mock.cpu_times.return_value = cpu_times(user=47.11, system=23.42)

    b = bazel.Bazel('foo', None)
    self.assertEqual({
        'wall': 98.76,
        'cpu': 47.11,
        'system': 23.42,
    }, b._get_times())

  @mock.patch.object(bazel.Bazel, '_get_pid', return_value=123)
  @mock.patch.object(bazel.Bazel, '_get_heap_size')
  @mock.patch.object(bazel.Bazel, '_get_times')
  @mock.patch.object(bazel.subprocess, 'Popen')
  @mock.patch('datetime.datetime')
  def test_command(self, datetime_mock, subprocess_mock, get_times_mock,
                   get_heap_size_mock, _):
    get_times_mock.side_effect = [
        {
            'wall': 42,
            'cpu': 0.5,
            'system': 12.3,
        },
        {
            'wall': 81.5,
            'cpu': 27.3,
            'system': 14.3,
        },
    ]
    get_heap_size_mock.side_effect = [700, 666, 668, 670, 667]
    process_mock = subprocess_mock.return_value
    process_mock.wait.return_value = 23
    datetime_mock.utcnow.return_value = 'fake_date'

    b = bazel.Bazel('foo', None)
    self.assertEqual({
        'wall': 39.5,
        'cpu': 26.8,
        'system': 2.0,
        'memory': 666,
        'exit_status': 23,
        'started_at': 'fake_date'
    }, b.command(
        command_name='build', args=['bar', 'zoo'], collect_memory=True))
    subprocess_mock.assert_called_with(
        ['foo', '--bazelrc=/dev/null', 'build', 'bar', 'zoo'], stdout=mock.ANY)


if __name__ == '__main__':
  unittest.main()
