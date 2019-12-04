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
# python3
"""Manages the configuration file for benchmarking.

Currently supported flags/attributes:
- project_commit
- project_source
- bazel_commit
- bazel_path
- runs
- collect_memory
- warmup_runs
- shutdown
- the command (which includes startup options, command, targets, command options)

Note that the pluralized options (e.g. --project_commits) have to repeated across
units or as a global option in their singular form.

Example of a config file:
benchmark_project_commits: False
global_options:
  project_commit: 223456789
  runs: 3
  collect_memory: true
  warmup_runs: 1
  shutdown: true
  bazelrc: null
  project_source: /path/to/project/repo
units:
 - bazel_commit: 273901377
   command: info
 - bazel_path: /tmp/bazel
   command: --host_jvm_debug build --nobuild //src:bazel
 - bazel_path: /tmp/bazel
   command: info
   project_commit: 987654321

The "benchmarking units" represent independent sets of conditions to be
benchmarked.

"""

import copy
import shlex
import yaml
import utils

from typing import Mapping, Sequence, Text, Union


class BenchmarkConfig(object):
  """Manages the configuration file for benchmarking."""

  # TODO(leba): have a single source of truth for this.
  # TODO(leba): Consider replacing dict with collections.namedtuple.
  _DEFAULT_VALS = {
      'bazel_commit': None,
      'project_commit': None,
      'runs': 3,
      'bazelrc': None,
      'collect_memory': False,
      'collect_profile': False,
      'warmup_runs': 1,
      'shutdown': True,
  }

  def __init__(self,
               units: Sequence[Mapping[Text, Union[Text, int]]],
               benchmark_project_commits: bool = False):
    """Loads the YAML config file and get the benchmarking units.

    Args:
      units: the benchmarking units.
      benchmark_project_commits: whether we're benchmarking depot CLs (instead of
        bazel commits). This makes a difference in how we generate our report.
    """
    self._units = units
    self._benchmark_project_commits = benchmark_project_commits

  def get_bazel_commits(self) -> Sequence[Union[Text, int]]:
    """Returns the list of specified bazel_commits."""
    return [
        unit['bazel_commit']
        for unit in self._units
        if 'bazel_commit' in unit and isinstance(unit['bazel_commit'], int)
    ]

  def get_units(self) -> Sequence[Mapping[Text, Union[Text, int]]]:
    """Returns a copy of the parsed units."""
    return copy.copy(self._units)

  def benchmark_project_commits(self) -> bool:
    """Returns whether we're benchmarking project commits (instead of bazel commits)."""
    return self._benchmark_project_commits

  @classmethod
  def from_file(cls, config_file_path: Text) -> 'BenchmarkConfig':
    """Loads the YAML config file and constructs a BenchmarkConfig.

    Args:
      config_file_path: the path to the configuration file.

    Returns:
      The created config object.
    """
    with open(config_file_path, 'r') as fi:
      return cls.from_string(fi.read())

  @classmethod
  def from_string(cls, string: Text) -> 'BenchmarkConfig':
    """Parses the content of a YAML config file and constructs a BenchmarkConfig.

    Args:
      string: a string in YAML file format. Usually the content of a config
        file.

    Returns:
      The created config object.
    """
    config = yaml.safe_load(string)
    if 'units' not in config:
      raise ValueError('Wrong config file format. Please check the example.')

    benchmark_project_commits = ('benchmark_project_commits' in config and
                           config['benchmark_project_commits'])

    global_options = (
        config['global_options'] if 'global_options' in config else {})

    parsed_units = []
    for local_options in config['units']:
      unit = copy.copy(global_options)
      # Local configs would override global ones.
      unit.update(local_options)
      parsed_units.append(cls._parse_unit(unit))
    return cls(parsed_units, benchmark_project_commits)

  @classmethod
  def from_flags(cls, bazel_commits: Union[Sequence[Text], Sequence[int]],
                 project_commits: Sequence[int], runs: int,
                 bazelrc: Text, collect_memory: bool,
                 collect_profile: bool, warmup_runs: int, shutdown: bool,
                 command: Text) -> 'BenchmarkConfig':
    """Creates the BenchmarkConfig based on specified flags.

    Args:
      bazel_commits: could be the bazel cl numbers, or paths to specific bazel
        versions.
      project_commits: the depot cls
      runs: The number of benchmark runs to perform for each combination.
      bazelrc: An optional path to a bazelrc.
      collect_memory: Whether to collect Blaze memory consumption.
      collect_profile: Whether to collect a JSON profile.
      warmup_runs: Number of warm-up runs that are discarded from the
        measurements.
      shutdown: Whether to shutdown Blaze during runs.
      command: the full command to benchmark, optionally with startup options
        prepended, e.g. "--noexobazel build --nobuild ...".

    Returns:
      The created config object.
    """
    units = []
    for bazel_commit in bazel_commits:
      for project_commit in project_commits:
        units.append(
            cls._parse_unit({
                'bazel_commit': bazel_commit,
                'project_commit': project_commit,
                'runs': runs,
                'bazelrc': bazelrc,
                'collect_memory': collect_memory,
                'collect_profile': collect_profile,
                'warmup_runs': warmup_runs,
                'shutdown': shutdown,
                'command': command,
            }))
    return cls(units, benchmark_project_commits=(len(project_commits) > 1))

  @classmethod
  def _parse_unit(
      cls, unit: Mapping[Text, Union[Text, int, bool]]
  ) -> Mapping[Text, Union[Text, int, bool]]:
    """Performs parsing of a benchmarking unit.

    Also fills up default values for attributes if they're not specified.

    Args:
      unit: the benchmarking unit.

    Returns:
      A dictionary that contains various attributes of the benchmarking unit.
    """
    parsed_unit = copy.copy(cls._DEFAULT_VALS)
    parsed_unit.update(unit)
    bazel_commit = unit['bazel_commit'] if 'bazel_commit' in unit else unit['bazel_path']
    if bazel_commit == 'HEAD':
      bazel_commit = utils.get_piper_head()
    parsed_unit['project_commit'] = (
        utils.get_piper_head()
        if unit['project_commit'] == 'HEAD' else unit['project_commit'])

    if 'command' not in unit or not isinstance(unit['command'], str):
      raise ValueError('A command has to be specified either as a global option'
                       ' or in each individual benchmarking unit.')
    full_command_tokens = shlex.split(unit['command'])
    startup_options = []
    while full_command_tokens and full_command_tokens[0].startswith('--'):
      startup_options.append(full_command_tokens.pop(0))
    try:
      command = full_command_tokens.pop(0)
    except IndexError:
      raise ValueError('\'%s\' does not contain a Blaze command (e.g. build)' %
                       unit['command'])
    options = []
    while full_command_tokens and full_command_tokens[0].startswith('--'):
      options.append(full_command_tokens.pop(0))
    targets = full_command_tokens

    # Attributes that need special handling.
    parsed_unit['startup_options'] = startup_options
    parsed_unit['command'] = command
    parsed_unit['options'] = options
    parsed_unit['targets'] = targets
    parsed_unit['bazel_commit'] = bazel_commit

    # This is necessary to maintain a consistent structure of the benchmark unit
    # objects.
    # TODO(leba) Clean this up.
    if 'bazel_path' in parsed_unit:
      del parsed_unit['bazel_path']

    return parsed_unit
