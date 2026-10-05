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
import collections
import io
import math
import os
import shutil
import tempfile
import unittest
from unittest import mock

import utils.bazel as bazel


class BazelTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    bazel._reset_known_output_bases()
    self.output_base = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.output_base)
    self.addCleanup(bazel._reset_known_output_bases)

  def _write_pid_file(self, pid):
    server_dir = os.path.join(self.output_base, 'server')
    os.makedirs(server_dir, exist_ok=True)
    with open(os.path.join(server_dir, 'server.pid.txt'), 'w') as f:
      f.write(str(pid))

  def _info_output(self, pid):
    return ('server_pid: %d\noutput_base: %s\n' % (pid, self.output_base)).encode()

  def test_get_pid_post_command(self):
    with mock.patch.object(
        bazel.subprocess, 'check_output', return_value=self._info_output(123)):
      b = bazel.Bazel('foo', [])
      self.assertEqual(123, b._get_pid_post_command())
      self.assertEqual(123, b._pid)

  def test_get_server_pid_reads_server_pid_file(self):
    self._write_pid_file(os.getpid())
    b = bazel.Bazel('foo', [], output_base=self.output_base)
    self.assertEqual(os.getpid(), b.get_server_pid())

  def test_get_server_pid_from_output_base_startup_option(self):
    self._write_pid_file(os.getpid())
    b = bazel.Bazel('foo', ['--output_base=%s' % self.output_base])
    self.assertEqual(os.getpid(), b.get_server_pid())

  def test_get_server_pid_without_output_base_does_not_start_server(self):
    with mock.patch.object(bazel.subprocess, 'check_output') as check_output_mock:
      b = bazel.Bazel('foo', [])
      self.assertIsNone(b.get_server_pid())
      check_output_mock.assert_not_called()

  def test_output_base_is_remembered_across_instances(self):
    # The benchmark creates a fresh Bazel object for every run. After the first run
    # discovered the output base, later instances must find the server via its PID
    # file without invoking `bazel info`.
    self._write_pid_file(os.getpid())
    with mock.patch.object(
        bazel.subprocess, 'check_output',
        return_value=self._info_output(os.getpid())):
      bazel.Bazel('foo', [])._get_pid_post_command()

    with mock.patch.object(bazel.subprocess, 'check_output') as check_output_mock:
      b = bazel.Bazel('foo', [])
      self.assertEqual(os.getpid(), b.get_server_pid())
      check_output_mock.assert_not_called()

    # Different startup options mean a different server.
    self.assertIsNone(bazel.Bazel('foo', ['--host_jvm_args=-Xmx1g']).get_server_pid())

  @mock.patch.object(bazel.Bazel, '_get_times_for_pid')
  @mock.patch.object(bazel.subprocess, 'check_call', return_value=0)
  def test_command_warm_server_reports_cpu_delta(self, _, get_times_mock):
    self._write_pid_file(os.getpid())
    get_times_mock.side_effect = [
        {'wall': 10.0, 'cpu': 100.0, 'system': 20.0},
        {'wall': 15.0, 'cpu': 104.0, 'system': 21.0},
    ]
    b = bazel.Bazel('foo', [], output_base=self.output_base)
    res = b.command('build', ['//:all'])

    self.assertEqual(4.0, res['cpu'])
    self.assertEqual(1.0, res['system'])
    self.assertEqual(
        [mock.call(os.getpid()), mock.call(os.getpid())], get_times_mock.call_args_list)

  @mock.patch.object(bazel.Bazel, '_get_times_for_pid')
  @mock.patch.object(bazel.subprocess, 'check_call', return_value=0)
  def test_command_server_restart_reports_full_cpu_of_new_server(self, check_call_mock,
                                                                 get_times_mock):
    self._write_pid_file(os.getpid())
    new_server_pid = os.getppid()

    def restart_server(*unused_args, **unused_kwargs):
      self._write_pid_file(new_server_pid)
      return 0

    check_call_mock.side_effect = restart_server
    get_times_mock.side_effect = [
        {'wall': 10.0, 'cpu': 100.0, 'system': 20.0},
        {'wall': 15.0, 'cpu': 7.0, 'system': 2.0},
    ]
    b = bazel.Bazel('foo', [], output_base=self.output_base)
    res = b.command('build', ['//:all'])

    self.assertEqual(7.0, res['cpu'])
    self.assertEqual(2.0, res['system'])

  def test_memory_sampler_reports_nan_without_server(self):
    sampler = bazel._ServerMemorySampler(lambda: None, interval_sec=0.001)
    sampler.start()
    self.assertTrue(math.isnan(sampler.stop()))

  def test_memory_sampler_picks_up_server_started_during_command(self):
    pids = [None, None, 42]

    def pid_getter():
      return pids.pop(0) if len(pids) > 1 else pids[0]

    with mock.patch.object(bazel, '_read_process_rss_mb', return_value=512.0):
      sampler = bazel._ServerMemorySampler(pid_getter, interval_sec=0.001)
      sampler.start()
      self.assertEqual(512.0, sampler.stop())

  @mock.patch.object(bazel.subprocess, 'check_output', return_value=b'280MB\n')
  def test_get_heap_size(self, _):
    b = bazel.Bazel('foo', [])
    self.assertEqual(280.0, b._get_heap_size())

  @mock.patch.object(bazel.time, 'time', return_value=100.0)
  @mock.patch.object(bazel.psutil, 'pid_exists', return_value=True)
  @mock.patch.object(bazel.psutil, 'Process')
  def test_get_times_for_pid(self, process_mock, unused_exists_mock, unused_time_mock):
    cpu_times = collections.namedtuple('cpu_times', 'user system')
    proc_mock = process_mock.return_value
    proc_mock.cpu_times.return_value = cpu_times(user=45.0, system=15.0)

    b = bazel.Bazel('foo', [])
    times = b._get_times_for_pid(123)
    self.assertEqual({'wall': 100.0, 'cpu': 45.0, 'system': 15.0}, times)

  @mock.patch.object(bazel.Bazel, '_get_pid_post_command', return_value=123)
  @mock.patch.object(bazel.Bazel, '_get_times_for_pid')
  @mock.patch.object(bazel.subprocess, 'check_call', return_value=0)
  @mock.patch.object(bazel.datetime, 'datetime')
  @mock.patch.object(bazel.time, 'time', side_effect=[10.0, 15.0])
  def test_command_without_memory_by_default(self, unused_time_mock, datetime_mock,
                                             subprocess_mock, get_times_mock, _):
    get_times_mock.side_effect = [
        {'wall': 10.0, 'cpu': 0.0, 'system': 0.0},
        {'wall': 15.0, 'cpu': 4.0, 'system': 1.0},
    ]
    datetime_mock.utcnow.return_value = 'fake_time'

    b = bazel.Bazel('foo', ['--host_jvm_args=-Xmx2g'])
    res = b.command('build', ['//:all'])

    self.assertEqual(0, res['exit_status'])
    self.assertEqual(5.0, res['wall'])
    self.assertEqual(4.0, res['cpu'])
    self.assertEqual(1.0, res['system'])
    self.assertNotIn('memory', res)

  @mock.patch.object(bazel.Bazel, '_get_times_for_pid',
                     return_value={'wall': 0.0, 'cpu': 1.0, 'system': 1.0})
  def test_command_cold_start_wall_excludes_pid_discovery(self, _):
    clock = [100.0]

    def fake_time():
      return clock[0]

    def fake_build(*unused_args, **unused_kwargs):
      clock[0] += 5.0  # The build itself takes 5s.
      return 0

    def fake_bazel_info(*unused_args, **unused_kwargs):
      clock[0] += 3.0  # `bazel info` takes 3s and must not be counted.
      return 123

    with mock.patch.object(bazel.time, 'time', side_effect=fake_time), \
         mock.patch.object(bazel.subprocess, 'check_call', side_effect=fake_build), \
         mock.patch.object(bazel.Bazel, '_get_pid_post_command',
                           side_effect=fake_bazel_info) as info_mock:
      res = bazel.Bazel('foo', []).command('build', ['//:all'])

    info_mock.assert_called_once()
    self.assertEqual(5.0, res['wall'])

  @mock.patch.object(bazel.Bazel, '_get_pid_post_command', return_value=123)
  @mock.patch.object(bazel.Bazel, '_get_times_for_pid')
  @mock.patch.object(bazel.Bazel, '_get_heap_size', return_value=250.0)
  @mock.patch.object(bazel.time, 'sleep')
  @mock.patch.object(bazel.subprocess, 'check_call', return_value=0)
  def test_command_with_collect_memory(self, subprocess_mock, sleep_mock,
                                       get_heap_mock, get_times_mock, _):
    get_times_mock.side_effect = [
        {'wall': 10.0, 'cpu': 0.0, 'system': 0.0},
        {'wall': 20.0, 'cpu': 5.0, 'system': 2.0},
    ]
    b = bazel.Bazel('foo', [])
    res = b.command('build', ['//:all'], collect_memory=True)

    self.assertEqual(250.0, res['memory'])
    self.assertTrue(get_heap_mock.called)

  def test_read_process_rss_mb(self):
    mock_status = "Name:\tbazel\nState:\tS\nRssAnon:\t  1048576 kB\nRssFile:\t   5000 kB\n"
    with mock.patch('builtins.open', mock.mock_open(read_data=mock_status)):
      rss = bazel._read_process_rss_mb(999)
      self.assertEqual(1024.0, rss)

  def test_shutdown_command(self):
    with mock.patch.object(bazel.subprocess, 'check_call', return_value=0):
      b = bazel.Bazel('foo', [])
      b._pid = 123
      res = b.command('shutdown')
      self.assertIsNone(res)
      self.assertIsNone(b._pid)


if __name__ == '__main__':
  unittest.main()
