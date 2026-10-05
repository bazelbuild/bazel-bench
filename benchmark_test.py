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
import collections
import math
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
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      benchmark._setup_project_repo('repo_path', 'project_source')

    mock_repo.git.fetch.assert_called_once_with('origin')
    self.assertEqual('Path repo_path exists. Updating...',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'chdir')
  def test_setup_project_repo_not_exists(self, unused_chdir_mock,
                                         unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      benchmark._setup_project_repo('repo_path', 'project_source')

    mock_repo_class.clone_from.assert_called_once_with('project_source',
                                                       'repo_path')
    self.assertEqual('Cloning project_source to repo_path...',
                     mock_stderr.getvalue())

  def test_get_commits_topological(self):
    with mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      mock_A = mock.MagicMock()
      mock_A.hexsha = 'A'
      mock_B = mock.MagicMock()
      mock_B.hexsha = 'B'
      mock_C = mock.MagicMock()
      mock_C.hexsha = 'C'
      mock_repo.iter_commits.return_value = [mock_C, mock_B, mock_A]
      mock_repo.git.rev_parse.side_effect = lambda x: x
      result = benchmark._get_commits_topological(['B', 'A'], mock_repo,
                                                  'flag_name')

      self.assertEqual(['A', 'B'], result)

  def test_get_commits_topological_latest(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      mock_commit = mock.MagicMock()
      mock_repo.commit.return_value = mock_commit
      mock_commit.hexsha = 'A'
      result = benchmark._get_commits_topological(None, mock_repo,
                                                  'bazel_commits')

    self.assertEqual(['A'], result)
    self.assertEqual('No bazel_commits specified, using the latest one: A',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=True)
  @mock.patch.object(benchmark.os, 'makedirs')
  def test_build_bazel_binary_exists(self, unused_chdir_mock,
                                     unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._build_bazel_binary('commit', 'repo_path', 'outroot')
    self.assertEqual('Binary exists at outroot/commit/bazel, reusing...',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'makedirs')
  @mock.patch.object(benchmark.os, 'chdir')
  @mock.patch.object(benchmark.shutil, 'copyfile')
  def test_build_bazel_binary_not_exists(self, unused_shutil_mock,
                                         unused_chdir_mock,
                                         unused_makedirs_mock,
                                         unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      benchmark._build_bazel_binary('commit', mock_repo, 'outroot')

    mock_repo.git.checkout.assert_called_once_with('-f', 'commit')
    self.assertEqual(
        ''.join([
            'Building Bazel binary at commit commit', 'bazel build //src:bazel',
            'Copying bazel binary to outroot/commit/bazel',
            'chmod +x outroot/commit/bazel'
        ]), mock_stderr.getvalue())

  def test_single_run(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._single_run(
          'bazel_binary_path',
          'build',
          options=[],
          targets=['//:all'],
          startup_options=[])

    self.assertEqual(
        ''.join([
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_no_prefetch(self, _):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=False,
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: None, PROJECT: None ===',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_prefetch(self, _):
    benchmark.DEFAULT_OUT_BASE_PATH = 'some_out_path'
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=True,
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: None, PROJECT: None ===',
            'Pre-fetching external dependencies...',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_collect_profile(self, _):
    benchmark.DEFAULT_OUT_BASE_PATH = 'some_out_path'
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=True,
          collect_profile=True,
          data_directory='fake_dir',
          bazel_identifier='fake_bazel_commit',
          project_commit='fake_project_commit',
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: fake_bazel_commit, PROJECT: fake_project_commit ===',
            'Pre-fetching external dependencies...',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --experimental_generate_json_trace_profile --profile=fake_dir/fake_uid_fake_bazel_commit_0_fake_project_commit_1_of_2.profile.gz --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --experimental_generate_json_trace_profile --profile=fake_dir/fake_uid_fake_bazel_commit_0_fake_project_commit_2_of_2.profile.gz --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_warmup_runs(self, _):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      collected, _ = benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=False,
          warmup_runs=1,
          unit_num=0)

    self.assertIn('Starting warmup run 1/1:', mock_stderr.getvalue())
    self.assertIn('Starting benchmark run 1/2:', mock_stderr.getvalue())
    self.assertIn('Starting benchmark run 2/2:', mock_stderr.getvalue())
    self.assertEqual(2, len(collected))

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_outlier_rerun(self, _):
    run_measurements = [
        {'wall': 10.0, 'cpu': 5.0, 'system': 1.0, 'exit_status': 0},
        {'wall': 100.0, 'cpu': 5.0, 'system': 1.0, 'exit_status': 0},
        {'wall': 10.1, 'cpu': 5.0, 'system': 1.0, 'exit_status': 0},
        {'wall': 9.9, 'cpu': 5.0, 'system': 1.0, 'exit_status': 0},
    ]
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
         mock.patch('benchmark._run_single_benchmark_iteration', side_effect=run_measurements):
      collected, _ = benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=3,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=False,
          max_outlier_reruns=1,
          unit_num=0)

    self.assertIn('Detected wall-time outlier (100.000s)', mock_stderr.getvalue())
    self.assertEqual(3, len(collected))
    self.assertEqual([10.0, 10.1, 9.9], [r['wall'] for r in collected])

  def test_create_summary(self):
    data = collections.OrderedDict()
    unit0 = {
        'wall': benchmark.Values([1.0, 1.1, 0.9]),
        'cpu': benchmark.Values([2.0, 2.1, 1.9]),
        'exit_status': benchmark.Values([0, 0, 0]),
    }
    unit1 = {
        'wall': benchmark.Values([0.5, 0.55, 0.45]),
        'cpu': benchmark.Values([1.0, 1.05, 0.95]),
        'exit_status': benchmark.Values([0, 0, 0]),
    }
    data[(0, 'bazel_1', 'commit_a')] = unit0
    data[(1, 'bazel_2', 'commit_a')] = unit1

    summary = benchmark.create_summary(data, 'project_source')
    self.assertIn('RESULTS:', summary)
    self.assertIn('[Unit #0]', summary)
    self.assertIn('[Unit #1]', summary)
    self.assertIn('wall:', summary)
    self.assertIn('cpu:', summary)
    self.assertIn('2.00', summary)
    self.assertIn('-0.500s, -50.0%', summary)

  def test_create_summary_unchanged_metrics(self):
    data = collections.OrderedDict()
    unit0 = {
        'wall': benchmark.Values([10.0, 10.0]),
        'memory': benchmark.Values([83.0, 83.0]),
        'actionsExecuted': benchmark.Values([1.0, 1.0]),
        'exit_status': benchmark.Values([0, 0]),
    }
    unit1 = {
        'wall': benchmark.Values([5.0, 5.0]),
        'memory': benchmark.Values([83.0, 83.0]),
        'actionsExecuted': benchmark.Values([1.0, 1.0]),
        'exit_status': benchmark.Values([0, 0]),
    }
    data[(0, 'bazel_1', 'commit_a')] = unit0
    data[(1, 'bazel_2', 'commit_a')] = unit1

    summary = benchmark.create_summary(data, '/tmp/project')
    lines = summary.splitlines()

    unit1_idx = -1
    for idx, l in enumerate(lines):
      if '[Unit #1]' in l:
        unit1_idx = idx
        break
    self.assertNotEqual(unit1_idx, -1)

    unit1_lines = lines[unit1_idx:]
    for line in unit1_lines:
      if 'memory:' in line:
        self.assertNotIn('1.00x', line)
        self.assertNotIn('+0.0%', line)
        self.assertNotIn('not significant', line)
      elif 'actionsExecuted:' in line:
        self.assertNotIn('1.00x', line)
        self.assertNotIn('+0.0%', line)
        self.assertNotIn('not significant', line)
      elif 'wall:' in line:
        self.assertIn('2.00x', line)

  def test_collect_metrics_pads_missing_metrics(self):
    results = [
        {'wall': 1.0, 'exit_status': 0, 'runner-worker': 3},
        {'wall': 2.0, 'exit_status': 1},
        {'wall': 3.0, 'exit_status': 0, 'runner-worker': 5, 'invocation_id': 'x'},
    ]
    collected = benchmark._collect_metrics(results)
    self.assertEqual([1.0, 2.0, 3.0], collected['wall'].values())
    worker = collected['runner-worker'].values()
    self.assertEqual(3, len(worker))
    self.assertEqual(3, worker[0])
    self.assertTrue(math.isnan(worker[1]))
    self.assertEqual(5, worker[2])
    self.assertEqual([None, None, 'x'], collected['invocation_id'].values())

  def test_create_summary_excludes_the_failed_run_for_sparse_metrics(self):
    # The failed run (index 1) did not report 'actionsExecuted'. Without
    # padding, excluding index 1 would drop the third run's value instead.
    results = [
        {'wall': 1.0, 'exit_status': 0, 'actionsExecuted': 10.0},
        {'wall': 1.0, 'exit_status': 1},
        {'wall': 1.0, 'exit_status': 0, 'actionsExecuted': 30.0},
    ]
    data = collections.OrderedDict()
    data[(0, 'bazel_1', 'commit_a')] = benchmark._collect_metrics(results)
    summary = benchmark.create_summary(data, 'src')
    line = [l for l in summary.splitlines() if l.startswith('actionsExecuted:')][0]
    self.assertIn('20', line)  # mean of 10 and 30

  def test_create_summary_compares_against_first_unit(self):
    data = collections.OrderedDict()
    for i, wall in enumerate([10.0, 5.0, 20.0]):
      data[(i, 'bazel_%d' % i, 'commit_a')] = {
          'wall': benchmark.Values([wall, wall * 1.01, wall * 0.99]),
          'exit_status': benchmark.Values([0, 0, 0]),
      }
    summary = benchmark.create_summary(data, 'src')
    self.assertIn('[Unit #0]', summary)
    unit0_header = [l for l in summary.splitlines() if l.startswith('[Unit #0]')][0]
    self.assertIn('(baseline)', unit0_header)
    unit2 = summary[summary.index('[Unit #2]'):]
    wall_line = [l for l in unit2.splitlines() if l.startswith('wall:')][0]
    # 20s vs. the 10s baseline (not vs. the previous unit's 5s).
    self.assertIn('+100.0%', wall_line)
    self.assertIn('0.50', wall_line)

  def test_create_summary_has_no_ansi_codes_by_default(self):
    data = collections.OrderedDict()
    data[(0, 'bazel_1', 'commit_a')] = {
        'wall': benchmark.Values([1.0, 1.1]),
        'exit_status': benchmark.Values([0, 0]),
    }
    self.assertNotIn('\033[', benchmark.create_summary(data, 'src'))
    self.assertIn('\033[1m', benchmark.create_summary(data, 'src', color=True))


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
    self.assertIn(
        ''.join([
            'FATAL Flags parsing error: flag --project_source=None: ',
            'Flag --project_source must have a value other than None.'
        ]), mock_stderr.getvalue())

  @flagsaver.flagsaver(bazel_commits=['a', 'b'], project_commits=['c', 'd'])
  def test_either_bazel_commits_project_commits_single_element(self):
    with self.assertRaises(ValueError) as context:
      benchmark._flag_checks()
    value_err = context.exception
    self.assertEqual(
        str(value_err),
        'Either --bazel_commits or --project_commits should be a single element.'
    )

  @flagsaver.flagsaver(clean=False)
  def test_single_run_skip_clean(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._single_run(
          'bazel_binary_path',
          'build',
          options=[],
          targets=['//:all'],
          startup_options=[])

    self.assertEqual(
        ''.join([
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @flagsaver.flagsaver(shutdown=False)
  def test_single_run_skip_shutdown(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._single_run(
          'bazel_binary_path',
          'build',
          options=[],
          targets=['//:all'],
          startup_options=[])

    self.assertEqual(
        ''.join([
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no'
        ]), mock_stderr.getvalue())


if __name__ == '__main__':
  absltest.main()
