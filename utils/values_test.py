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
import unittest

from values import Values


class ValuesTest(unittest.TestCase):

  def test_initialize(self):
    values = Values()
    self.assertEqual([], values.values())

    values = Values([2.3, 4.2])
    self.assertEqual([2.3, 4.2], values.values())

  def test_add(self):
    values = Values()
    self.assertEqual([], values.values())

    values.add(4.2)
    values.add(2.3)
    self.assertEqual([4.2, 2.3], values.values())

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

  def test_pval_identical(self):
    identical_list = [1, 10, 1]
    values = Values(identical_list)
    self.assertEqual(0, values.pval(identical_list))

  def test_pval_significant(self):
    values = Values([1, 1, 1])
    self.assertAlmostEqual(0.900, values.pval([10, 10, 10]), places=3)


if __name__ == '__main__':
  unittest.main()
