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
"""Handles Bazel invocations and measures their time/memory consumption."""
import datetime
import math
import os
import subprocess
import tempfile
import threading
import time
from typing import Mapping, Sequence, Optional, Dict, Any, Tuple

import psutil
import utils.logger as logger


def _read_process_rss_mb(pid: int) -> float:
  """Returns anonymous RSS memory in MB from /proc/<pid>/status."""
  if not pid or pid <= 0:
    return 0.0
  status_path = f'/proc/{pid}/status'
  try:
    with open(status_path, 'r') as f:
      for line in f:
        if line.startswith('RssAnon:'):
          return float(line.split()[1]) / 1024.0
  except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, ValueError):
    pass
  return 0.0


class _ServerMemorySampler:
  """Samples the Bazel server RSS at regular intervals during command execution."""

  def __init__(self, pid_getter, interval_sec: float = 0.05):
    self._pid_getter = pid_getter
    self._interval_sec = interval_sec
    self._stop_event = threading.Event()
    self._thread: Optional[threading.Thread] = None
    self.peak_rss_mb: float = 0.0
    self._saw_pid = False

  def start(self) -> None:
    self._sample_once()
    self._thread = threading.Thread(target=self._sample_loop, daemon=True)
    self._thread.start()

  def _sample_once(self) -> None:
    try:
      pid = self._pid_getter()
      if pid and pid > 0:
        self._saw_pid = True
        rss_mb = _read_process_rss_mb(pid)
        if rss_mb > self.peak_rss_mb:
          self.peak_rss_mb = rss_mb
    except Exception:
      pass

  def _sample_loop(self) -> None:
    while not self._stop_event.is_set():
      self._sample_once()
      self._stop_event.wait(self._interval_sec)

  def stop(self) -> float:
    """Stops sampling and returns the peak RSS in MB, or NaN if no server was ever seen."""
    self._stop_event.set()
    if self._thread:
      self._thread.join(timeout=1.0)
    self._sample_once()
    return self.peak_rss_mb if self._saw_pid else math.nan


# Output bases of Bazel servers seen so far, keyed by (binary, startup options, cwd).
# The benchmark creates a new Bazel object for every run, so the output base has to
# outlive the instance; otherwise every run looks like a cold start and the server
# PID (needed for CPU deltas and RSS sampling) is unknown while the command runs.
_known_output_bases: Dict[Tuple[str, Tuple[str, ...], str], str] = {}


def _reset_known_output_bases() -> None:
  """Forgets all remembered output bases. For tests."""
  _known_output_bases.clear()


class Bazel(object):
  """Class to handle Bazel invocations.

  Allows measuring resource consumption of each command non-invasively.

  Attributes:
    bazel_binary_path: Path to the bazel binary to be invoked.
    startup_options: Sequence of startup options.
  """

  def __init__(self, bazel_binary_path: str, startup_options: Optional[Sequence[str]] = None,
               output_base: Optional[str] = None):
    self._bazel_binary_path = str(bazel_binary_path)
    self._startup_options = list(startup_options) if startup_options else []
    self._server_key = (self._bazel_binary_path, tuple(self._startup_options), os.getcwd())
    self._output_base = (
        output_base
        or self._output_base_from_startup_options()
        or _known_output_bases.get(self._server_key))
    self._pid: Optional[int] = None

  def _output_base_from_startup_options(self) -> Optional[str]:
    for opt in self._startup_options:
      if opt.startswith('--output_base='):
        return os.path.abspath(os.path.expanduser(opt[len('--output_base='):]))
    return None

  def _set_output_base(self, output_base: str) -> None:
    self._output_base = output_base
    _known_output_bases[self._server_key] = output_base

  def _get_server_pid_from_file(self) -> Optional[int]:
    """Reads the server PID from <output_base>/server/server.pid.txt if the output base is known."""
    if not self._output_base:
      return None
    pid_file = os.path.join(self._output_base, 'server', 'server.pid.txt')
    try:
      with open(pid_file, 'r') as f:
        pid = int(f.read().strip())
      if psutil.pid_exists(pid):
        return pid
    except (ValueError, OSError):
      pass
    return None

  def get_server_pid(self) -> Optional[int]:
    """Returns the PID of the running Bazel server without starting one prematurely."""
    if self._pid and psutil.pid_exists(self._pid):
      return self._pid
    file_pid = self._get_server_pid_from_file()
    if file_pid:
      self._pid = file_pid
      return self._pid
    return None

  def _get_pid_post_command(self) -> Optional[int]:
    """Discovers server PID (and output base) after command execution."""
    # Re-read the PID file: the server may have been restarted by the command.
    self._pid = None
    pid = self.get_server_pid()
    if pid:
      return pid
    try:
      cmd = [self._bazel_binary_path] + self._startup_options + [
          'info', 'server_pid', 'output_base'
      ]
      out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
      info = {}
      for line in out.splitlines():
        key, sep, value = line.partition(':')
        if sep:
          info[key.strip()] = value.strip()
      if info.get('output_base'):
        self._set_output_base(info['output_base'])
      self._pid = int(info['server_pid'])
      return self._pid
    except (subprocess.CalledProcessError, KeyError, ValueError, OSError):
      return None

  def _get_times_for_pid(self, pid: Optional[int]) -> Dict[str, float]:
    """Retrieves current wall, cpu (user), and system times for a process."""
    wall = time.time()
    if pid and psutil.pid_exists(pid):
      try:
        proc = psutil.Process(pid=pid)
        cpu_times = proc.cpu_times()
        return {'wall': wall, 'cpu': cpu_times.user, 'system': cpu_times.system}
      except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return {'wall': wall, 'cpu': 0.0, 'system': 0.0}

  def _get_heap_size(self) -> float:
    """Retrieves retained heap size in MB via `bazel info used-heap-size-after-gc`."""
    try:
      cmd = [self._bazel_binary_path] + self._startup_options + ['info', 'used-heap-size-after-gc']
      raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
      if raw.endswith('MB'):
        raw = raw[:-2]
      return float(raw)
    except (subprocess.CalledProcessError, ValueError, OSError):
      return float('nan')

  def command(self, command: str, args: Optional[Sequence[str]] = None,
              collect_memory: bool = False,
              collect_process_memory: bool = False) -> Optional[Dict[str, Any]]:
    """Invokes a command with the Bazel binary and measures resource consumption.

    Args:
      command: The bazel command (e.g. 'build', 'test', 'clean', 'shutdown').
      args: Additional command line arguments.
      collect_memory: If True, measures retained heap size via GC inspection.
      collect_process_memory: If True, samples peak anonymous process RSS.

    Returns:
      A dictionary of collected metrics or None if command was 'shutdown'.
    """
    args = list(args) if args else []
    logger.log('Executing Bazel command: bazel %s %s %s' %
               (' '.join(self._startup_options), command, ' '.join(args)))

    result: Dict[str, Any] = {'started_at': datetime.datetime.utcnow()}
    before_pid = self.get_server_pid()
    before_times = self._get_times_for_pid(before_pid)

    memory_sampler = None
    if collect_process_memory and command != 'shutdown':
      memory_sampler = _ServerMemorySampler(self.get_server_pid)
      memory_sampler.start()

    exit_status = 0
    with tempfile.NamedTemporaryFile() as tmp_stderr:
      full_cmd = [self._bazel_binary_path] + self._startup_options + [command] + args
      with open(os.devnull, 'w') as dev_null:
        start_wall = time.time()
        try:
          subprocess.check_call(full_cmd, stdout=dev_null, stderr=tmp_stderr.file)
        except subprocess.CalledProcessError as e:
          exit_status = e.returncode
      # Take the end timestamp right away, before any bookkeeping (logging,
      # stopping the sampler, PID discovery, heap inspection).
      end_wall = time.time()
      if exit_status != 0:
        logger.log_error('Bazel command failed with exit code %s' % exit_status)
        tmp_stderr.seek(0)
        logger.log_error(tmp_stderr.read().decode())

    if memory_sampler:
      result['peakProcessRss'] = memory_sampler.stop()

    if command == 'shutdown':
      self._pid = None
      return None

    # Fast path: re-read the PID file (no subprocess, the server may have been
    # restarted by the command) and sample CPU times immediately.
    self._pid = None
    server_pid = self.get_server_pid()
    if server_pid:
      after_times = self._get_times_for_pid(server_pid)
    else:
      # Output base unknown (first cold start): discover it via `bazel info`.
      # The (small) CPU cost of that call is unavoidably attributed to this
      # command, but it is excluded from the wall time.
      server_pid = self._get_pid_post_command()
      after_times = self._get_times_for_pid(server_pid)
    if server_pid != before_pid:
      # The command started (or restarted) the server: all of its CPU time belongs
      # to this command.
      before_times = {'wall': before_times['wall'], 'cpu': 0.0, 'system': 0.0}

    result['wall'] = end_wall - start_wall
    result['cpu'] = max(0.0, after_times['cpu'] - before_times['cpu'])
    result['system'] = max(0.0, after_times['system'] - before_times['system'])
    result['exit_status'] = exit_status

    if collect_memory:
      heap = self._get_heap_size()
      for _ in range(2):
        time.sleep(1)
        next_heap = self._get_heap_size()
        if not math.isnan(next_heap):
          heap = min(heap, next_heap) if not math.isnan(heap) else next_heap
      result['memory'] = heap

    return result
