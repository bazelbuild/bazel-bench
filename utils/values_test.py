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
"""Unit tests for benchmark values utility class."""
import math
import unittest

from utils.values import Values


class ValuesTest(unittest.TestCase):

  def test_initialize(self):
    values = Values()
    self.assertEqual([], values.values())
    self.assertTrue(values.empty())

    values = Values([2.3, 4.2])
    self.assertEqual([2.3, 4.2], values.values())
    self.assertFalse(values.empty())

  def test_add_and_merge(self):
    values = Values()
    values.add(4.2)
    values.add(2.3)
    self.assertEqual([4.2, 2.3], values.values())

    other = Values([10.0, 20.0])
    values.merge(other)
    self.assertEqual([4.2, 2.3, 10.0, 20.0], values.values())

  def test_min_and_max(self):
    values = Values([5.0, 2.0, 9.0, 1.0])
    self.assertEqual(1.0, values.min())
    self.assertEqual(9.0, values.max())

  def test_median(self):
    values = Values([1, 10, 1])
    self.assertEqual(1, values.median())

    # Returns the average of the two middle values when len(values()) is even.
    values.add(20)
    self.assertEqual(5.5, values.median())

    values.add(20)
    self.assertEqual(10, values.median())

  def test_mean(self):
    values = Values([1, 10, 1])
    self.assertEqual(4, values.mean())

  def test_stddev(self):
    values = Values([1, 10, 1])
    self.assertAlmostEqual(4.24, values.stddev(), places=2)

  def test_nan_handling(self):
    values = Values([10.0, float('nan'), 20.0])
    self.assertEqual([10.0, 20.0], values.values_wo_nan())
    self.assertEqual(15.0, values.mean())
    self.assertEqual(15.0, values.median())
    self.assertEqual(10.0, values.min())
    self.assertEqual(20.0, values.max())

  def test_confidence_interval(self):
    values = Values([10.0, 11.0, 9.0, 10.5, 9.5])
    low, high = values.confidence(0.95)
    self.assertTrue(low < values.mean() < high)
    self.assertAlmostEqual(10.0, values.mean(), delta=0.1)

    # Single value returns nan
    single = Values([5.0])
    low, high = single.confidence()
    self.assertTrue(math.isnan(low) and math.isnan(high))

  def test_outlier_detection_mad(self):
    # Cluster around 10.0 with one severe outlier (100.0)
    raw = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 100.0]
    values = Values(raw)
    inliers, outliers = values.get_inliers_and_outliers(z_score_cutoff=1.5)

    self.assertIn(100.0, outliers.values())
    self.assertNotIn(100.0, inliers.values())
    self.assertEqual(6, len(inliers.values()))
    self.assertEqual(1, len(outliers.values()))

  def test_outlier_detection_mad_zero(self):
    # More than half equal to median
    raw = [5.0, 5.0, 5.0, 5.0, 12.0]
    values = Values(raw)
    inliers, outliers = values.get_inliers_and_outliers()
    self.assertEqual([5.0, 5.0, 5.0, 5.0], inliers.values())
    self.assertEqual([12.0], outliers.values())

  def test_get_outlier_indices(self):
    raw = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 100.0]
    values = Values(raw)
    self.assertEqual([6], values.get_outlier_indices(z_score_cutoff=1.5))

  def test_get_outlier_indices_few_values(self):
    values = Values([10.0, 100.0])
    self.assertEqual([], values.get_outlier_indices())

  def test_pval_identical(self):
    identical_list = [1, 10, 1]
    values = Values(identical_list)
    self.assertEqual(0, values.pval(identical_list))
    self.assertEqual("not significant", values.significance_label(identical_list))

  def test_pval_significant(self):
    values = Values([1, 1, 1, 1, 1])
    base = [10, 10, 10, 10, 10]
    p = values.pval(base)
    self.assertAlmostEqual(0.992, p, places=3)
    self.assertEqual("significant", values.significance_label(base))

  def test_speedup_ratio(self):
    # Baseline takes 20s, new version takes 10s -> 2.0x speedup (-50% wall time)
    base = Values([19.9, 20.1, 20.0, 20.0])
    curr = Values([9.9, 10.1, 10.0, 10.0])
    ratio, err, pct_diff = curr.speedup_ratio(base)

    self.assertAlmostEqual(2.0, ratio, delta=0.05)
    self.assertAlmostEqual(-50.0, pct_diff, delta=0.5)
    self.assertTrue(err > 0.0)

  def test_is_regression(self):
    base = Values([10.0, 10.0, 10.0, 10.0, 10.0])
    slower = Values([20.0, 20.0, 20.0, 20.0, 20.0])
    faster = Values([5.0, 5.0, 5.0, 5.0, 5.0])

    self.assertTrue(slower.is_regression(base, pval_threshold=0.90))
    self.assertFalse(faster.is_regression(base, pval_threshold=0.90))


if __name__ == '__main__':
  unittest.main()
