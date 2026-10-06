# Copyright 2026 The Bazel Authors. All rights reserved.
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
"""Tests for utils/bisection.py."""

import os
import shutil
import subprocess
import tempfile
import unittest

import git

from utils import bisection
from utils.values import Values


class BisectionTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.repo_dir = os.path.join(self.temp_dir, 'repo')
    os.makedirs(self.repo_dir)

    # Initialize a git repository with default branch main and files ref format
    try:
      subprocess.run(['git', 'init', '--ref-format=files', '-b', 'main'], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
      subprocess.run(['git', 'init', '-b', 'main'], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)

    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=self.repo_dir, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=self.repo_dir, check=True)

    self.repo = git.Repo(self.repo_dir)

    # Create 5 commits
    self.commits = []
    for i in range(5):
      fpath = os.path.join(self.repo_dir, 'dummy.txt')
      with open(fpath, 'w') as f:
        f.write(f'Version {i}\n')
      subprocess.run(['git', 'add', '.'], cwd=self.repo_dir, check=True)
      subprocess.run(['git', 'commit', '-m', f'Commit {i}'], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)
      sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo_dir, capture_output=True, text=True, check=True).stdout.strip()
      self.commits.append(sha)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def test_get_commit_range(self):
    range_commits = bisection.get_commit_range(self.repo, self.commits[0], self.commits[4])
    self.assertEqual(self.commits[1:5], range_commits)

  def test_bisect_identifies_culprit(self):
    # c0 (good) -> c1 (good) -> c2 (culprit regression) -> c3 (bad) -> c4 (bad)
    c0, c1, c2, c3, c4 = self.commits

    perf_map = {
        c0: Values([10.0, 10.0, 10.0, 10.0, 10.0]),
        c1: Values([10.1, 9.9, 10.0, 10.0, 10.0]),
        c2: Values([20.0, 20.1, 19.9, 20.0, 20.0]),  # regression introduced here!
        c3: Values([20.0, 20.2, 19.8, 20.1, 20.0]),
        c4: Values([20.5, 20.0, 19.9, 20.1, 20.2]),
    }

    eval_count = 0
    def eval_fn(commit):
      nonlocal eval_count
      eval_count += 1
      return perf_map[commit]

    result = bisection.bisect(
        self.repo,
        good_commit=c0,
        bad_commit=c4,
        eval_fn=eval_fn,
        target_metric='wall',
        pval_threshold=0.90)

    self.assertEqual(c2, result.culprit_commit)
    self.assertEqual(c0, result.good_commit)
    self.assertEqual(c4, result.bad_commit)
    summary_text = result.summary()
    self.assertIn('=== BISECTION RESULT ===', summary_text)
    self.assertIn(f'Culprit commit: {c2}', summary_text)
    self.assertTrue(eval_count <= len(self.commits))

  def test_bisect_single_commit_range(self):
    c1, c2 = self.commits[1], self.commits[2]
    def eval_fn(commit):
      return Values([10.0] * 5 if commit == c1 else [20.0] * 5)

    result = bisection.bisect(
        self.repo,
        good_commit=c1,
        bad_commit=c2,
        eval_fn=eval_fn,
        target_metric='wall')

    self.assertEqual(c2, result.culprit_commit)


  def test_bisect_reports_no_culprit_when_bad_is_not_a_regression(self):
    c0, c4 = self.commits[0], self.commits[4]
    evaluated = []

    def eval_fn(commit):
      evaluated.append(commit)
      return Values([10.0, 10.1, 9.9, 10.0, 10.0])

    result = bisection.bisect(self.repo, c0, c4, eval_fn, target_metric='wall')

    self.assertIsNone(result.culprit_commit)
    # Only the two endpoints are measured.
    self.assertEqual([c0, c4], evaluated)
    self.assertIn('Culprit commit: none', result.summary())

  def test_bisect_ignores_smaller_unrelated_regression(self):
    # c1 has a small (+5%) but significant regression; the real (+100%)
    # regression is introduced by c3.
    c0, c1, c2, c3, c4 = self.commits
    perf_map = {
        c0: Values([10.0, 10.0, 10.0, 10.0, 10.0]),
        c1: Values([10.5, 10.5, 10.5, 10.5, 10.5]),
        c2: Values([10.5, 10.5, 10.5, 10.5, 10.5]),
        c3: Values([20.0, 20.0, 20.0, 20.0, 20.0]),
        c4: Values([20.0, 20.0, 20.0, 20.0, 20.0]),
    }
    result = bisection.bisect(
        self.repo, c0, c4, lambda c: perf_map[c], target_metric='wall')
    self.assertEqual(c3, result.culprit_commit)

  def test_bisect_fails_on_missing_measurements(self):
    c0, c4 = self.commits[0], self.commits[4]

    def eval_fn(commit):
      # e.g. misspelled metric name, or all runs failed.
      return Values()

    with self.assertRaisesRegex(bisection.BisectError, 'No successful measurements'):
      bisection.bisect(self.repo, c0, c4, eval_fn, target_metric='wal')


if __name__ == '__main__':
  unittest.main()
