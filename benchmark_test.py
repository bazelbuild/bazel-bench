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
"""Tests for the main benchmarking script."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import mock
import sys
import benchmark
import six

from absl.testing import absltest
from absl.testing import flagsaver
from absl import flags
from testutils.fakes import fake_log, fake_exec_command, FakeBazel

# Setup custom fakes/mocks.
benchmark.logger.log = fake_log
benchmark._exec_command = fake_exec_command
benchmark.Bazel = FakeBazel
mock_stdio_type = six.StringIO


class BenchmarkFunctionTests(absltest.TestCase):

  @mock.patch.object(benchmark.os.path, 'exists', return_value=True)
  @mock.patch.object(benchmark.os, 'chdir')
  def test_setup_project_repo_exists(self, unused_chdir_mock,
                                     unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._setup_project_repo('repo_path', 'project_source')
    self.assertEqual(''.join([
        "Path repo_path exists. Updating...",
        "['git', 'checkout', 'master']",
        "['git', '-C', 'repo_path', 'pull', 'origin', 'master']"]),
        mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'chdir')
  def test_setup_project_repo_not_exists(self, unused_chdir_mock,
                                         unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._setup_project_repo('repo_path', 'project_source')
    self.assertEqual(''.join([
        "Cloning project_source to repo_path...",
        "['git', 'clone', 'project_source', 'repo_path']"]),
        mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_checkout_project_commit_latest(self, _):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._checkout_project_commit('latest', 'project_path')
    self.assertTrue(len(mock_stderr.getvalue()) == 0)

  @mock.patch.object(benchmark.os, 'chdir')
  def test_checkout_project_commit_hash(self, _):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._checkout_project_commit('some_hash', 'project_path')
    self.assertEqual("['git', 'checkout', '-f', 'some_hash']",
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=True)
  @mock.patch.object(benchmark.os, 'makedirs')
  def test_build_bazel_binary_exists(self, unused_chdir_mock,
                                     unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._build_bazel_binary('commit', 'repo_path', 'outroot/')
    self.assertEqual('Binary exists at outroot/commit, reusing...',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'makedirs')
  @mock.patch.object(benchmark.os, 'chdir')
  @mock.patch.object(benchmark.shutil, 'copyfile')
  def test_build_bazel_binary_not_exists(
      self, unused_shutil_mock, unused_chdir_mock, unused_makedirs_mock,
      unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._build_bazel_binary('commit', 'repo_path', 'outroot/')
    self.assertEqual(''.join([
        "['git', 'checkout', '-f', 'commit']",
        "['bazel', 'build', '//src:bazel']",
        'Copying bazel binary to outroot/commit',
        "['chmod', '+x', 'outroot/commit']"]), mock_stderr.getvalue())

  def test_single_run(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._single_run(
          'bazel_binary_path',
          'build',
          expressions=['//:all'],
          options=[],
          bazelrc=None,
          collect_memory=False)

    self.assertEqual(''.join([
        'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ']), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  @mock.patch.object(benchmark.args_parser, 'parse_bazel_args_from_canonical_str')
  def test_run_benchmark_no_prefetch(self, args_parser_mock, _):
    runs = 2
    args_parser_mock.return_value = ('build', [], ['//:all'])
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs,
          collect_memory=False,
          bazel_args=['build', '//:all'],
          bazelrc=None,
          prefetch_ext_deps=False)

    self.assertEqual(''.join([
        'Parsing arguments from command line...',
        'Starting benchmark run 1/2:',
        'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ',
        'Starting benchmark run 2/2:',
        'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ']), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  @mock.patch.object(benchmark.args_parser, 'parse_bazel_args_from_build_event')
  def test_run_benchmark_prefetch(self, args_parser_mock, _):
    runs = 2
    args_parser_mock.return_value = ('build', [], ['//:all'])
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs,
          collect_memory=False,
          bazel_args=['build', '//:all'],
          bazelrc=None,
          prefetch_ext_deps=True)

    self.assertEqual(''.join([
        'Pre-fetching external dependencies & exporting build env json to /tmp/.bazel-bench/out/build_env.json...',
        'Executing Bazel command: bazel build //:all --build_event_json_file=/tmp/.bazel-bench/out/build_env.json',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ',
        'Starting benchmark run 1/2:',
        'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ',
        'Starting benchmark run 2/2:',
        'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
        'Executing Bazel command: bazel clean --color=no',
        'Executing Bazel command: bazel shutdown ']), mock_stderr.getvalue())


class BenchmarkFlagsTest(absltest.TestCase):

  @flagsaver.flagsaver
  def test_project_source_present(self):
    # This mirrors the requirement in benchmark.py
    flags.mark_flag_as_required('project_source')
    # Assert that the script fails when no project_source is specified
    with mock.patch.object(
        sys, 'stderr', new=mock_stdio_type()) as mock_stderr, self.assertRaises(
            SystemExit) as context:
      benchmark.app.run(benchmark.main)
    self.assertIn(''.join([
        'FATAL Flags parsing error: flag --project_source=None: ',
        'Flag --project_source must have a value other than None.']),
        mock_stderr.getvalue())

  @flagsaver.flagsaver(bazel_commits=['a', 'b'], project_commits=['c', 'd'])
  def test_either_bazel_commits_project_commits_single_element(self):
    with self.assertRaises(ValueError) as context:
      benchmark._flag_checks()
    value_err = context.exception
    self.assertEqual(
        value_err.message,
        'Either --bazel_commits or --project_commits should be a single element.'
    )

  @flagsaver.flagsaver(upload_data_to='wrong_pattern')
  def test_upload_data_to_wrong_pattern(self):
    with self.assertRaises(ValueError) as context:
      benchmark._flag_checks()
    value_err = context.exception
    self.assertEqual(
        value_err.message,
        '--upload_data_to should follow the pattern ' \
        '<dataset_id>:<table_id>:<location>')

  @flagsaver.flagsaver(upload_data_to='correct:flag:pattern')
  @mock.patch.object(benchmark.os, 'environ', return_value={})
  def test_upload_data_to_no_credentials(self, _):
    with self.assertRaises(ValueError) as context:
      benchmark._flag_checks()
    value_err = context.exception
    self.assertEqual(
        value_err.message,
        'GOOGLE_APPLICATION_CREDENTIALS is required to upload data to bigquery.')

if __name__ == '__main__':
  absltest.main()
