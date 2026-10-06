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
"""Tests for utils.bep."""
import json
import math
import os
import tempfile
import unittest

from utils import bep


class BepTest(unittest.TestCase):

  def test_get_bep_flags(self):
    flags = bep.get_bep_flags('/tmp/bep.json')
    self.assertEqual(['--build_event_json_file=/tmp/bep.json'], flags)

  def test_parse_empty_or_nonexistent_file(self):
    metrics = bep.parse_bep_json_file('/nonexistent/path/bep.json')
    self.assertTrue(math.isnan(metrics['actionsCreated']))
    self.assertTrue(math.isnan(metrics['actionsExecuted']))
    self.assertTrue(math.isnan(metrics['remoteCacheHits']))
    self.assertTrue(math.isnan(metrics['actionCacheHits']))

  def test_absent_cache_counters_are_zero_when_action_summary_present(self):
    events = [{'buildMetrics': {'actionSummary': {'actionsExecuted': '5'}}}]
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
      for event in events:
        tmp.write(json.dumps(event) + '\n')
      tmp_path = tmp.name
    try:
      metrics = bep.parse_bep_json_file(tmp_path)
      self.assertEqual(0, metrics['remoteCacheHits'])
      self.assertEqual(0, metrics['diskCacheHits'])
      # No actionCacheStatistics at all: unknown rather than zero.
      self.assertTrue(math.isnan(metrics['actionCacheHits']))
    finally:
      os.unlink(tmp_path)

  def test_parse_bep_json_events(self):
    events = [
        {"started": {"uuid": "test-uuid-1234"}},
        {
            "buildMetrics": {
                "actionSummary": {
                    "actionsCreated": 150,
                    "actionsExecuted": 42,
                    "runnerCount": [
                        {"name": "total", "count": 52},
                        {"name": "worker", "count": 30},
                        {"name": "remote", "count": 12},
                        {"name": "remote cache hit", "count": 7},
                        {"name": "disk cache hit", "count": 3},
                    ],
                    # int64 fields are strings in proto3 JSON.
                    "actionCacheStatistics": {"hits": "108", "misses": "42"},
                },
                "buildGraphMetrics": {
                    "outputArtifactCount": 200,
                },
                "packageMetrics": {
                    "packagesLoaded": 85,
                },
                "targetMetrics": {
                    "targetsConfigured": 320,
                },
                "memoryMetrics": {
                    "peakPostGcHeapSize": 524288000,  # 500 MB
                    "usedHeapSizePostBuild": 262144000,  # 250 MB
                    "garbageMetrics": [
                        {"type": "G1 Eden Space", "garbageCollected": 104857600},  # 100 MB
                        {"type": "G1 Old Gen", "garbageCollected": 52428800},  # 50 MB
                    ],
                },
                "timingMetrics": {
                    "analysisPhaseTimeInMs": 1250,
                    "executionPhaseTimeInMs": 4800,
                },
            }
        },
    ]

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
      for event in events:
        tmp.write(json.dumps(event) + '\n')
      tmp_path = tmp.name

    try:
      metrics = bep.parse_bep_json_file(tmp_path)
      self.assertEqual("test-uuid-1234", metrics['invocation_id'])
      self.assertEqual(150.0, metrics['actionsCreated'])
      self.assertEqual(42.0, metrics['actionsExecuted'])
      self.assertEqual(200.0, metrics['outputArtifactCount'])
      self.assertEqual(85.0, metrics['packagesLoaded'])
      self.assertEqual(320.0, metrics['targetsConfigured'])
      self.assertAlmostEqual(500.0, metrics['peakPostGcHeapSize'], places=1)
      self.assertAlmostEqual(250.0, metrics['usedHeapSizePostBuild'], places=1)
      self.assertAlmostEqual(100.0, metrics['edenSpaceGarbage'], places=1)
      self.assertAlmostEqual(50.0, metrics['oldGenGarbage'], places=1)
      self.assertAlmostEqual(1.25, metrics['analysisPhaseTime'], places=2)
      self.assertAlmostEqual(4.8, metrics['executionPhaseTime'], places=2)
      self.assertEqual(7, metrics['remoteCacheHits'])
      self.assertEqual(3, metrics['diskCacheHits'])
      self.assertEqual(108, metrics['actionCacheHits'])
      self.assertEqual(42, metrics['actionCacheMisses'])
      self.assertEqual(30, metrics['runner-worker'])
      self.assertEqual(12, metrics['runner-remote'])
    finally:
      os.unlink(tmp_path)


if __name__ == '__main__':
  unittest.main()
