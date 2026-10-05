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
"""Automated Git bisection for Bazel performance regressions."""

from typing import Callable, Dict, List, Optional
import git
import utils.logger as logger
from utils.values import Values


class BisectError(Exception):
  """Raised when a bisection cannot produce a meaningful result."""


class BisectResult(object):
  """Container for git bisection results.

  culprit_commit is None when the bad commit turned out not to be a regression
  relative to the good commit.
  """

  def __init__(self, culprit_commit: Optional[str], good_commit: str, bad_commit: str,
               target_metric: str, evaluations: Dict[str, Values], commit_list: List[str]):
    self.culprit_commit = culprit_commit
    self.good_commit = good_commit
    self.bad_commit = bad_commit
    self.target_metric = target_metric
    self.evaluations = evaluations
    self.commit_list = commit_list

  def summary(self) -> str:
    """Formats human-readable bisection report."""
    lines = []
    lines.append('=== BISECTION RESULT ===')
    lines.append('Target metric:  %s' % self.target_metric)
    lines.append('Good commit:    %s' % self.good_commit)
    lines.append('Bad commit:     %s' % self.bad_commit)
    lines.append('Total commits:  %d' % len(self.commit_list))
    lines.append('Evaluated:      %d commits' % len(self.evaluations))

    good_vals = self.evaluations.get(self.good_commit)
    if self.culprit_commit is None:
      lines.append('Culprit commit: none (no significant regression between good and bad)')
      bad_vals = self.evaluations.get(self.commit_list[-1]) if self.commit_list else None
      if good_vals is not None and bad_vals is not None:
        lines.append('Good mean:      %.3f, Bad mean: %.3f' % (good_vals.mean(), bad_vals.mean()))
      return '\n'.join(lines)

    lines.append('Culprit commit: %s' % self.culprit_commit)
    culprit_vals = self.evaluations.get(self.culprit_commit)
    if good_vals is not None and culprit_vals is not None:
      ratio, _, pct = culprit_vals.speedup_ratio(good_vals)
      lines.append('Baseline mean:  %.3f, Culprit mean: %.3f (%+.1f%%, ratio: %.2fx)' %
                   (good_vals.mean(), culprit_vals.mean(), pct, ratio))
    return '\n'.join(lines)


def get_commit_range(repo: git.Repo, good_commit: str, bad_commit: str) -> List[str]:
  """Returns list of commit SHAs between good_commit and bad_commit in chronological order."""
  rev_range = f'{good_commit}..{bad_commit}'
  commits = list(repo.iter_commits(rev_range))
  return [c.hexsha for c in reversed(commits)]


def _evaluate(eval_fn: Callable[[str], Values], commit: str, target_metric: str) -> Values:
  """Runs eval_fn and fails loudly if it produced no usable measurements."""
  values = eval_fn(commit)
  if values is None or not values.values_wo_nan():
    raise BisectError(
        'No successful measurements of metric %r for commit %s. Either the metric '
        'name is wrong or all benchmark runs failed for this commit.' %
        (target_metric, commit))
  return values


def bisect(repo: git.Repo,
           good_commit: str,
           bad_commit: str,
           eval_fn: Callable[[str], Values],
           target_metric: str = 'wall',
           pval_threshold: float = 0.95,
           min_effect_fraction: float = 0.5) -> BisectResult:
  """Performs binary search between good_commit and bad_commit to find first regressing commit.

  The bad commit is measured first; if it is not a significant regression over
  the good commit, the bisection stops and reports no culprit.

  A commit counts as "bad" only if it is a statistically significant
  regression over the good commit AND its median has moved at least
  min_effect_fraction of the way from the good median to the bad median. The
  latter prevents an unrelated, smaller regression earlier in the range from
  being reported as the culprit.

  Args:
    repo: git.Repo instance.
    good_commit: Baseline commit without regression.
    bad_commit: Target commit exhibiting regression.
    eval_fn: Callable taking commit SHA and returning Values for target_metric,
      containing only measurements of successful runs.
    target_metric: Name of metric being bisected.
    pval_threshold: Statistical significance threshold for KS test (default 0.95).
    min_effect_fraction: Fraction of the good->bad median difference a commit
      must exhibit to be considered bad (default 0.5).

  Returns:
    BisectResult containing the culprit commit (or None) and evaluation details.

  Raises:
    BisectError: if a commit yields no usable measurements.
    ValueError: if the commit range is empty.
  """
  logger.log('Starting bisection for %s between %s and %s...' %
             (target_metric, good_commit, bad_commit))
  commit_list = get_commit_range(repo, good_commit, bad_commit)
  if not commit_list:
    raise ValueError(f'No commits found in range {good_commit}..{bad_commit}')

  evaluations: Dict[str, Values] = {}

  logger.log('Evaluating good commit %s...' % good_commit)
  good_values = _evaluate(eval_fn, good_commit, target_metric)
  evaluations[good_commit] = good_values

  last_commit = commit_list[-1]
  logger.log('Evaluating bad commit %s...' % bad_commit)
  bad_values = _evaluate(eval_fn, last_commit, target_metric)
  evaluations[last_commit] = bad_values

  if not bad_values.is_regression(good_values, pval_threshold):
    logger.log_warn(
        'Bad commit %s is not a significant regression of %s over good commit %s '
        '(good mean=%.3f, bad mean=%.3f). Nothing to bisect.' %
        (bad_commit, target_metric, good_commit, good_values.mean(), bad_values.mean()))
    return BisectResult(None, good_commit, bad_commit, target_metric, evaluations, commit_list)

  good_median = good_values.median()
  threshold = good_median + min_effect_fraction * (bad_values.median() - good_median)

  def is_bad(values: Values) -> bool:
    return values.is_regression(good_values, pval_threshold) and values.median() >= threshold

  low = 0
  high = len(commit_list) - 1  # Verified bad above.

  while low < high:
    mid = (low + high) // 2
    mid_commit = commit_list[mid]
    logger.log('Bisection step: testing commit [%d/%d] %s...' % (mid + 1, len(commit_list), mid_commit))

    if mid_commit not in evaluations:
      evaluations[mid_commit] = _evaluate(eval_fn, mid_commit, target_metric)
    mid_values = evaluations[mid_commit]

    mid_is_bad = is_bad(mid_values)
    logger.log('Commit %s bad=%s (mid_median=%.3f, good_median=%.3f, threshold=%.3f)' %
               (mid_commit, mid_is_bad, mid_values.median(), good_median, threshold))

    if mid_is_bad:
      high = mid
    else:
      low = mid + 1

  culprit = commit_list[low]
  logger.log('Bisection identified culprit commit: %s' % culprit)
  return BisectResult(culprit, good_commit, bad_commit, target_metric, evaluations, commit_list)
