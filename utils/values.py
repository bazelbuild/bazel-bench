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
"""Stores a set of numeric values and offers statistical operations on them."""
import copy
import math
from typing import Sequence, Tuple, Optional

import numpy
import scipy.stats


class Values(object):
  """Utility class to store numeric values and calculate statistics.

  Used to collect and compare metrics during benchmarking.

  Attributes:
    items: An optional list of numeric values to initialize the data structure with.
  """

  def __init__(self, items: Optional[Sequence[float]] = None):
    self._items = list(items) if items is not None else []

  def add(self, value: float) -> None:
    """Adds value to the list of stored values."""
    self._items.append(value)

  def merge(self, other: 'Values') -> None:
    """Merges all values from another Values instance."""
    self._items.extend(other.values())

  def empty(self) -> bool:
    """Returns True if no items are stored."""
    return len(self._items) == 0

  def values(self) -> list[float]:
    """Returns the list of stored values."""
    return self._items

  def items(self) -> list[float]:
    """Returns a copy of the stored values."""
    return copy.copy(self._items)

  def values_wo_nan(self) -> list[float]:
    """Returns the list of stored values excluding non-finite values (NaN/Inf)."""
    return [x for x in self._items if math.isfinite(x)]

  def mean(self) -> float:
    """Returns the mean of the stored values (excluding NaNs)."""
    vals = self.values_wo_nan()
    if not vals:
      return math.nan
    return float(numpy.mean(vals))

  def median(self) -> float:
    """Returns the median of the stored values (excluding NaNs)."""
    vals = self.values_wo_nan()
    if not vals:
      return math.nan
    return float(numpy.median(vals))

  def min(self) -> float:
    """Returns the minimum of the stored values (excluding NaNs)."""
    vals = self.values_wo_nan()
    if not vals:
      return math.nan
    return float(min(vals))

  def max(self) -> float:
    """Returns the maximum of the stored values (excluding NaNs)."""
    vals = self.values_wo_nan()
    if not vals:
      return math.nan
    return float(max(vals))

  def stddev(self) -> float:
    """Returns the standard deviation of the stored values (excluding NaNs)."""
    vals = self.values_wo_nan()
    if not vals:
      return math.nan
    return float(numpy.std(vals))

  def confidence(self, confidence_level: float = 0.95) -> Tuple[float, float]:
    """Returns the confidence interval of the stored values (excluding NaNs).

    Args:
      confidence_level: The confidence level (default: 0.95 for 95% CI).

    Returns:
      A tuple of (low, high) representing the confidence interval.
    """
    vals = self.values_wo_nan()
    if len(vals) < 2:
      return (math.nan, math.nan)
    sem = scipy.stats.sem(vals)
    if sem == 0.0:
      mean_val = self.mean()
      return (mean_val, mean_val)
    interval = scipy.stats.t.interval(
        confidence_level,
        len(vals) - 1,
        loc=self.mean(),
        scale=sem,
    )
    return (float(interval[0]), float(interval[1]))

  def get_inliers_and_outliers(self, z_score_cutoff: float = 1.5) -> Tuple['Values', 'Values']:
    """Partitions values into inliers and outliers using Modified Z-Score with MAD.

    Modified Z-score = 0.6745 * |x - median| / MAD.
    Values with Modified Z-score > z_score_cutoff are considered outliers.

    Args:
      z_score_cutoff: Modified Z-score threshold (default: 1.5).

    Returns:
      A tuple (inliers, outliers) of Values instances.
    """
    mod_z_score_factor = 0.6745
    vals = self.values_wo_nan()
    if not vals:
      return (Values(), Values())

    med = self.median()
    median_differences = [abs(med - item) for item in vals]
    mad = float(numpy.median(median_differences))

    inliers = Values()
    outliers = Values()

    if mad == 0:
      # Special case: more than half of values equal the median.
      for item in vals:
        if item == med:
          inliers.add(item)
        else:
          outliers.add(item)
    else:
      for item in vals:
        score = mod_z_score_factor * abs(med - item) / mad
        if score <= z_score_cutoff:
          inliers.add(item)
        else:
          outliers.add(item)

    return (inliers, outliers)

  def get_inliers(self, z_score_cutoff: float = 1.5) -> 'Values':
    """Returns the subset of inliers after outlier removal."""
    inliers, _ = self.get_inliers_and_outliers(z_score_cutoff)
    return inliers

  def get_outliers(self, z_score_cutoff: float = 1.5) -> 'Values':
    """Returns the subset of outliers detected."""
    _, outliers = self.get_inliers_and_outliers(z_score_cutoff)
    return outliers

  def pval(self, base_values: Sequence[float]) -> float:
    """Computes Kolmogorov-Smirnov statistic against base_values.

    Args:
      base_values: A sequence of numeric values to compare with.

    Returns:
      1 - p, representing confidence that the two samples differ.
      Returns -1 if fewer than 2 values exist in either sample.
    """
    vals = self.values_wo_nan()
    base_vals = [b for b in base_values if math.isfinite(b)]
    if len(vals) > 1 and len(base_vals) > 1:
      _, p = scipy.stats.ks_2samp(vals, base_vals)
      return float(1.0 - p)
    return -1.0

  def significance_label(self, base_values: Sequence[float]) -> str:
    """Returns human-readable significance classification comparing against base_values."""
    p_stat = self.pval(base_values)
    if p_stat < 0.0:
      return "insufficient data"
    if p_stat < 0.90:
      return "not significant"
    if p_stat < 0.95:
      return "weakly significant"
    return "significant"

  def speedup_ratio(self, base_values: 'Values') -> Tuple[float, float, float]:
    """Calculates relative speedup/slowdown ratio of this metric relative to baseline.

    Args:
      base_values: The baseline Values object.

    Returns:
      A tuple of (ratio, ratio_error, percent_diff) where:
        ratio = base_mean / self_mean (>1.0 means this run is faster)
        ratio_error = propagated standard error of the ratio
        percent_diff = 100 * (self_mean - base_mean) / base_mean
    """
    base_mean = base_values.mean()
    self_mean = self.mean()
    if math.isnan(base_mean) or math.isnan(self_mean) or self_mean == 0.0 or base_mean == 0.0:
      return (math.nan, math.nan, math.nan)

    ratio = base_mean / self_mean
    percent_diff = 100.0 * (self_mean - base_mean) / base_mean

    # Error propagation for ratio R = A / B:
    # (sigma_R / R)^2 = (sem_A / A)^2 + (sem_B / B)^2
    vals_self = self.values_wo_nan()
    vals_base = base_values.values_wo_nan()
    if len(vals_self) > 1 and len(vals_base) > 1:
      sem_self = scipy.stats.sem(vals_self)
      sem_base = scipy.stats.sem(vals_base)
      rel_err_sq = (sem_base / base_mean) ** 2 + (sem_self / self_mean) ** 2
      ratio_error = ratio * math.sqrt(rel_err_sq)
    else:
      ratio_error = 0.0

    return (ratio, ratio_error, percent_diff)

  def is_regression(self, base_values: 'Values', pval_threshold: float = 0.95) -> bool:
    """Determines if there is a statistically significant regression compared to baseline."""
    if self.empty() or base_values.empty():
      return False
    return self.median() > base_values.median() and self.pval(base_values.values()) >= pval_threshold

  def exclude_from_indexes(self, indexes: Sequence[int]) -> 'Values':
    """Returns a copy of Values excluding items at specified indices."""
    filtered = [val for i, val in enumerate(self._items) if i not in indexes]
    return Values(filtered)
