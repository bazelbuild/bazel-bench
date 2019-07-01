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
""""Stores a set of numeric values and offers statistical operations on them."""
import numpy
import scipy.stats
import copy

class Values(object):
  """Utility class to store numeric values.

  This class is used in order to collect and compare metrics during
  benchmarking.

  Attributes:
    items: An optional list of numeric values to initialize the data structure
      with.
  """

  def __init__(self, items=None):
    self._items = items or []

  def add(self, value):
    """Adds value to the list of stored values."""
    self._items.append(value)

  def values(self):
    """Returns the list of stored values."""
    return self._items

  def mean(self):
    """Returns the mean of the stored values."""
    return numpy.mean(self._items)

  def median(self):
    """Returns the median of the stored values."""
    return numpy.median(self._items)

  def stddev(self):
    """Returns the standard deviation of the stored values."""
    return float(numpy.std(self._items))

  def pval(self, base_values):
    """Computes Kolmogorov-Smirnov statistic.

    Args:
      base_values: A list of numeric values to compare self.values() with.

    Returns:
      The probability for the null hypothesis that the samples drawn from the
      same distribution.
      Returns -1 if it cannot be computed because one of the samples contains
      less than 2 values.
    """
    vals = self._items
    if len(vals) > 1 and len(base_values) > 1:
      _, p = scipy.stats.ks_2samp(vals, base_values)
      return 1 - p
    else:
      return -1

  def items(self):
    return copy.copy(self._items)

