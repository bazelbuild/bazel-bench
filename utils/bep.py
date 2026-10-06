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
"""Build Event Protocol (BEP) metrics extractor for bazel-bench."""
import json
import math
import os
from typing import Dict, Any, Optional, List


# Runner names Bazel reports in actionSummary.runnerCount for cache hits.
_REMOTE_CACHE_HIT_RUNNER = 'remote cache hit'
_DISK_CACHE_HIT_RUNNER = 'disk cache hit'


def get_bep_flags(bep_output_path: str) -> List[str]:
  """Returns the bazel flags needed to generate a JSON Build Event Protocol file."""
  return [f'--build_event_json_file={bep_output_path}']


def parse_bep_json_file(bep_path: str) -> Dict[str, Any]:
  """Parses a newline-delimited JSON BEP file and extracts build and performance metrics.

  Args:
    bep_path: Path to the BEP JSON file.

  Returns:
    A dictionary containing extracted metrics:
      - invocation_id: UUID of the build invocation
      - actionsCreated: Total actions created during analysis
      - actionsExecuted: Total actions executed
      - outputArtifactCount: Total output artifacts created
      - packagesLoaded: Number of packages loaded during loading phase
      - targetsConfigured: Number of targets configured during analysis
      - peakPostGcHeapSize: Peak heap size post major GC in MB
      - usedHeapSizePostBuild: Retained heap size post build in MB
      - edenSpaceGarbage: Total garbage collected in Eden space in MB
      - oldGenGarbage: Total garbage collected in Old Gen in MB
      - analysisPhaseTime: Duration of analysis phase in seconds
      - executionPhaseTime: Duration of execution phase in seconds
      - actionCacheHits: Actions skipped thanks to the local action cache
        (actionSummary.actionCacheStatistics.hits)
      - actionCacheMisses: Local action cache misses
      - remoteCacheHits: Actions served from the remote cache (runner
        "remote cache hit")
      - diskCacheHits: Actions served from the disk cache (runner
        "disk cache hit")
      - runner-<name>: Execution count per runner (e.g. runner-worker, runner-remote)
  """
  metrics: Dict[str, Any] = {
      'actionsCreated': math.nan,
      'actionsExecuted': math.nan,
      'outputArtifactCount': math.nan,
      'packagesLoaded': math.nan,
      'targetsConfigured': math.nan,
      'peakPostGcHeapSize': math.nan,
      'usedHeapSizePostBuild': math.nan,
      'edenSpaceGarbage': math.nan,
      'oldGenGarbage': math.nan,
      'actionCacheHits': math.nan,
      'actionCacheMisses': math.nan,
      'remoteCacheHits': math.nan,
      'diskCacheHits': math.nan,
  }

  if not os.path.exists(bep_path):
    return metrics

  try:
    with open(bep_path, 'r', encoding='utf-8') as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        try:
          event = json.loads(line)
        except json.JSONDecodeError:
          continue

        # Invocation ID
        if 'started' in event and 'uuid' in event['started']:
          metrics['invocation_id'] = event['started']['uuid']

        # Build metrics event
        if 'buildMetrics' in event:
          bm = event['buildMetrics']

          # Action metrics
          if 'actionSummary' in bm:
            act = bm['actionSummary']
            if 'actionsCreated' in act:
              metrics['actionsCreated'] = float(act['actionsCreated'])
            if 'actionsExecuted' in act:
              metrics['actionsExecuted'] = float(act['actionsExecuted'])
            # Proto3 JSON omits zero-valued fields, so once an actionSummary is
            # present, absent counters mean 0.
            metrics['remoteCacheHits'] = 0
            metrics['diskCacheHits'] = 0
            for runner in act.get('runnerCount', []):
              name = runner.get('name', 'unknown')
              count = int(runner.get('count', 0))
              metrics[f'runner-{name}'] = count
              if name == _REMOTE_CACHE_HIT_RUNNER:
                metrics['remoteCacheHits'] = count
              elif name == _DISK_CACHE_HIT_RUNNER:
                metrics['diskCacheHits'] = count
            if 'actionCacheStatistics' in act:
              stats = act['actionCacheStatistics']
              # int64 fields are encoded as strings in proto3 JSON.
              metrics['actionCacheHits'] = int(stats.get('hits', 0))
              metrics['actionCacheMisses'] = int(stats.get('misses', 0))

          # Build graph metrics
          if 'buildGraphMetrics' in bm:
            bgm = bm['buildGraphMetrics']
            if 'outputArtifactCount' in bgm:
              metrics['outputArtifactCount'] = float(bgm['outputArtifactCount'])

          # Package metrics
          if 'packageMetrics' in bm:
            pm = bm['packageMetrics']
            if 'packagesLoaded' in pm:
              metrics['packagesLoaded'] = float(pm['packagesLoaded'])

          # Target metrics
          if 'targetMetrics' in bm:
            tm = bm['targetMetrics']
            if 'targetsConfigured' in tm:
              metrics['targetsConfigured'] = float(tm['targetsConfigured'])

          # Memory metrics
          if 'memoryMetrics' in bm:
            mm = bm['memoryMetrics']
            if 'peakPostGcHeapSize' in mm:
              metrics['peakPostGcHeapSize'] = float(mm['peakPostGcHeapSize']) / (1024 * 1024)
            if 'usedHeapSizePostBuild' in mm:
              metrics['usedHeapSizePostBuild'] = float(mm['usedHeapSizePostBuild']) / (1024 * 1024)
            if 'garbageMetrics' in mm:
              for item in mm['garbageMetrics']:
                g_type = item.get('type', '')
                bytes_collected = float(item.get('garbageCollected', 0))
                mb_collected = bytes_collected / (1024 * 1024)
                if 'Eden' in g_type:
                  metrics['edenSpaceGarbage'] = mb_collected
                elif 'Old' in g_type:
                  metrics['oldGenGarbage'] = mb_collected

          # Timing metrics
          if 'timingMetrics' in bm:
            timing = bm['timingMetrics']
            if 'analysisPhaseTimeInMs' in timing:
              metrics['analysisPhaseTime'] = float(timing['analysisPhaseTimeInMs']) / 1000.0
            if 'executionPhaseTimeInMs' in timing:
              metrics['executionPhaseTime'] = float(timing['executionPhaseTimeInMs']) / 1000.0

  except (IOError, OSError):
    pass

  return metrics
