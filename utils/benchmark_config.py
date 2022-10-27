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
"""Manages the configuration file for benchmarking.

Currently supported flags/attributes:
- project_commit
- project_source
- bazel_commit
- bazel_binary
- runs
- collect_profile
- the command (which includes startup options, command, targets, command
options)

Note that the pluralized options (e.g. --project_commits) have to repeated
across units or as a global option in their singular form.

Example of a config file:
benchmark_project_commits: False
global_options:
  project_commit: 595a730
  runs: 5
  collect_profile: false
  project_source: /path/to/project/repo
units:
 - bazel_commit: 595a730
   command: info
 - bazel_binary: /tmp/bazel
   command: --host_jvm_debug build --nobuild //src:bazel
 - bazel_binary: /tmp/bazel
   command: info
   project_commit: 595a731

The "benchmarking units" represent independent sets of conditions to be
benchmarked.

"""

import copy
import shlex
import sys
import yaml
import sys


class BenchmarkConfig(object):
  """Manages the configuration file for benchmarking."""

  # TODO(leba): have a single source of truth for this.
  # TODO(leba): Consider replacing dict with collections.namedtuple.
  _DEFAULT_VALS = {
      'runs': 5,
      'collect_profile': False,
      'bazel_source': 'https://github.com/bazelbuild/bazel.git',
      'env_configure': None,
  }

  def __init__(self, units, benchmark_project_commits=False):
    """Loads the YAML config file and get the benchmarking units.

    Args:
      units: the benchmarking units.
      benchmark_project_commits: whether we're benchmarking project commits
        (instead of bazel commits). This makes a difference in how we generate
        our report.
    """
    self._units = units
    self._benchmark_project_commits = benchmark_project_commits

  def get_units(self):
    """Returns a copy of the parsed units."""
    return copy.copy(self._units)

  def get_bazel_commits(self):
    """Returns the list of specified bazel_commits."""
    return [
        unit['bazel_commit'] for unit in self._units if 'bazel_commit' in unit
    ]

  def get_project_commits(self):
    """Returns the list of specified project_commits."""
    return [
        unit['project_commit'] for unit in self._units if 'project_commit' in unit
    ]

  def get_project_source(self):
    """Returns the common project_source across the units.

    We don't allow multiple project_source for now.
    """
    return None if not self._units else self._units[0]['project_source']

  def get_bazel_source(self):
    """Returns the common bazel_source across the units.

    We don't allow multiple bazel_source for now.
    """
    return None if not self._units else self._units[0]['bazel_source']

  def benchmark_project_commits(self):
    """Returns whether we're benchmarking project commits (instead of bazel commits)."""
    return self._benchmark_project_commits

  @classmethod
  def from_file(cls, config_file_path):
    """Loads the YAML config file and constructs a BenchmarkConfig.

    Args:
      config_file_path: the path to the configuration file.

    Returns:
      The created config object.
    """
    with open(config_file_path, 'r') as fi:
      return cls.from_string(fi.read())

  @classmethod
  def from_string(cls, string):
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
  def from_flags(cls, bazel_commits, bazel_binaries, project_commits,
                 bazel_source, project_source, env_configure, runs,
                 collect_profile, command):
    """Creates the BenchmarkConfig based on specified flags.

    Args:
      bazel_commits: the bazel commits.
      bazel_binaries: paths to pre-built bazel binaries.
      project_commits: the project commits.
      bazel_source: Either a path to the local Bazel repo or a https url to a
        GitHub repository
      project_source: Either a path to the local git project to be built or a
        https url to a GitHub repository
      env_configure: The command to run on the project repository before building it.
      runs: The number of benchmark runs to perform for each combination.
      collect_profile: Whether to collect a JSON profile.
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
                'bazel_source': bazel_source,
                'project_source': project_source,
                'runs': runs,
                'collect_profile': collect_profile,
                'env_configure': env_configure,
                'command': command,
            }))
    for bazel_binary in bazel_binaries:
      for project_commit in project_commits:
        units.append(
            cls._parse_unit({
                'bazel_binary': bazel_binary,
                'project_commit': project_commit,
                'bazel_source': bazel_source,
                'project_source': project_source,
                'runs': runs,
                'collect_profile': collect_profile,
                'env_configure': env_configure,
                'command': command,
            }))
    return cls(units, benchmark_project_commits=(len(project_commits) > 1))

  @classmethod
  def _parse_unit(cls, unit):
    """Performs parsing of a benchmarking unit.

    Also fills up default values for attributes if they're not specified.

    Args:
      unit: the benchmarking unit.

    Returns:
      A dictionary that contains various attributes of the benchmarking unit.
    """
    parsed_unit = copy.copy(cls._DEFAULT_VALS)
    parsed_unit.update(unit)

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
    while full_command_tokens and full_command_tokens[0].startswith('--') and full_command_tokens[0] != '--':
      options.append(full_command_tokens.pop(0))
    # This is a workaround for https://github.com/bazelbuild/bazel/issues/3236.
    if sys.platform.startswith('linux'):
      options.append('--sandbox_tmpfs_path=/tmp')

    targets = full_command_tokens

    # Attributes that need special handling.
    parsed_unit['startup_options'] = startup_options
    parsed_unit['command'] = command
    parsed_unit['options'] = options
    parsed_unit['targets'] = targets

    return parsed_unit
