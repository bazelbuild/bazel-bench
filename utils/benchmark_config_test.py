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
"""Tests for benchmark_config."""

import benchmark_config
import unittest
import os
import tempfile

class BenchmarkConfigTest(unittest.TestCase):

  def test_parsing_from_file(self):
    file_content = """
units:
 - bazel_commit: hash1
   project_commit: hash1
   command: info
"""
    _, config_file_path = tempfile.mkstemp()
    with open(config_file_path, 'w') as tf:
      tf.write(file_content)
    result = benchmark_config.BenchmarkConfig.from_file(config_file_path)

    self.assertEqual(result._units, [{
        'bazel_commit': 'hash1',
        'project_commit': 'hash1',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': False,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'info',
        'startup_options': [],
        'options': [],
        'targets': []
    }])
    self.assertEqual(result._benchmark_project_commits, False)
    os.remove(config_file_path)

  def test_parsing_from_string(self):
    file_content = """
benchmark_project_commits: False
global_options:
  project_commit: 'hash3'
  runs: 3
  collect_memory: true
  warmup_runs: 1
  shutdown: true
  bazelrc: null
units:
 - bazel_commit: hash1
   command: info
 - bazel_path: /tmp/bazel
   command: build --nobuild //abc
   project_commit: 'hash2'
"""
    result = benchmark_config.BenchmarkConfig.from_string(file_content)

    self.assertEqual(result._units, [{
        'bazel_commit': 'hash1',
        'project_commit': 'hash3',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'info',
        'startup_options': [],
        'options': [],
        'targets': []
    }, {
        'bazel_path': '/tmp/bazel',
        'project_commit': 'hash2',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'build',
        'startup_options': [],
        'options': ['--nobuild'],
        'targets': ['//abc']
    }])
    self.assertEqual(result._benchmark_project_commits, False)

  def test_parsing_from_flags(self):
    result = benchmark_config.BenchmarkConfig.from_flags(
        bazel_commits=['hash1', 'hash2'],
        project_commits=['hash3'],
        runs=3,
        bazelrc=None,
        collect_memory=True,
        collect_profile=False,
        warmup_runs=1,
        shutdown=True,
        command='build --nobuild //abc')
    self.assertEqual(result._units, [{
        'bazel_commit': 'hash1',
        'project_commit': 'hash3',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'build',
        'startup_options': [],
        'options': ['--nobuild'],
        'targets': ['//abc']
    }, {
        'bazel_commit': 'hash2',
        'project_commit': 'hash3',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'build',
        'startup_options': [],
        'options': ['--nobuild'],
        'targets': ['//abc']
    }])
    self.assertEqual(result._benchmark_project_commits, False)

  def test_get_units(self):
    config = benchmark_config.BenchmarkConfig([{
        'bazel_commit': 'hash1',
        'project_commit': 'hash2',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'info',
        'startup_options': [],
        'options': [],
        'targets': []
    }, {
        'bazel_commit': '/tmp/bazel',
        'project_commit': 'hash2',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'build',
        'startup_options': [],
        'options': ['--nobuild'],
        'targets': ['//abc']
    }])
    self.assertEqual(config.get_units() is config._units, False)
    self.assertEqual(config.get_units() == config._units, True)

  def test_bazel_commits(self):
    config = benchmark_config.BenchmarkConfig([{
        'bazel_commit': 'hash1',
        'project_commit': 'hash2',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'info',
        'startup_options': [],
        'options': [],
        'targets': []
    }, {
        'bazel_path': '/tmp/bazel',
        'project_commit': 'hash2',
        'runs': 3,
        'bazelrc': None,
        'collect_memory': True,
        'collect_profile': False,
        'warmup_runs': 1,
        'shutdown': True,
        'command': 'build',
        'startup_options': [],
        'options': ['--nobuild'],
        'targets': ['//abc']
    }])
    self.assertEqual(config.get_bazel_commits(), ['hash1'])


if __name__ == '__main__':
  unittest.main()
