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
import os
import subprocess
import hashlib
import shutil
import collections
import utils.logger as logger
import utils.bazel_args_parser as args_parser

from absl import app
from absl import flags
from absl.flags import argparse_flags

from utils.values import Values
from utils.bazel import Bazel
from utils.output_handling import export_csv, upload_csv

# The path to the cloned bazelbuild/bazel repo.
BAZEL_CLONE_PATH = '/tmp/.bazel-bench/bazel'
# The path to the clone of the project to be built with Bazel.
PROJECT_CLONE_BASE_PATH = '/tmp/.bazel-bench/project-clones/'
BAZEL_GITHUB_URL = 'https://github.com/bazelbuild/bazel.git'
# The path to the directory that stores the bazel binaries.
BAZEL_BINARY_BASE_PATH = '/tmp/.bazel-bench/bazel-bin/'
# The path to the directory that stores the output csv (If required).
DEFAULT_OUT_BASE_PATH = '/tmp/.bazel-bench/out/'


def _get_clone_subdir(project_source):
  """Calculates a hexdigest of project_source to serve as a unique subdir name."""
  return hashlib.md5(project_source).hexdigest()


def _exec_command(args, shell=False, fail_if_nonzero=True):
  logger.log('Executing: %s' % ' '.join(args))

  if FLAGS.verbose:
    return subprocess.call(args, shell=shell)

  fd_devnull = open(os.devnull, 'w')
  return subprocess.call(
      args, shell=shell, stdout=fd_devnull, stderr=fd_devnull)


def _setup_project_repo(repo_path, project_source):
  """Returns a path to the cloned repository.

  Args:
    repo_path: the path to clone the repository to.
    project_source: the source to clone the repository from. Could be a local
      path or an URL.

  Returns:
    The path to the cloned repository.
    If the repo_path exists, perform a `git pull` to update the content.
    Else, clone the project to repo_path.
  """
  if os.path.exists(repo_path):
    os.chdir(repo_path)
    logger.log('Path %s exists. Updating...' % repo_path)
    _exec_command(['git', 'checkout', 'master'])
    _exec_command(['git', '-C', repo_path, 'pull', 'origin', 'master'])
  else:
    logger.log('Cloning %s to %s...' % (project_source, repo_path))
    _exec_command(['git', 'clone', project_source, repo_path])
    os.chdir(repo_path)

  return repo_path


def _checkout_project_commit(commit, project_path):
  """Checks out the project at the specified commit.

  Do nothing if commit is set to 'latest'.

  Args:
    commit: the commit hash to check out.
    project_path: the path to the cloned repository.
  """
  os.chdir(project_path)
  if commit == 'latest':
    return
  _exec_command(['git', 'checkout', '-f', commit])


def _build_bazel_binary(commit, repo_path, outroot):
  """Builds bazel at the specified commit and copy the output binary to outroot.

  If the binary for this commit already exists at the destination path, simply
  return the path without re-building.

  Args:
    commit: the Bazel commit.
    repo_path: the path to the Bazel repository.
    outroot: the directory inwhich the resulting binary is copied to.

  Returns:
    The path to the resulting binary (copied to outroot).
  """
  destination = outroot + commit
  if os.path.exists(destination):
    logger.log('Binary exists at %s, reusing...' % destination)
    return destination

  _checkout_project_commit(commit, repo_path)
  _exec_command(['bazel', 'build', '//src:bazel'])

  # Copy to another location
  binary_out = '%s/bazel-bin/src/bazel' % repo_path
  destination = outroot + commit

  if not os.path.exists(outroot):
    os.makedirs(outroot)
  logger.log('Copying bazel binary to %s' % destination)
  shutil.copyfile(binary_out, destination)
  _exec_command(['chmod', '+x', destination])

  return destination


def _single_run(bazel_binary_path,
                command,
                expressions,
                options,
                bazelrc=None,
                collect_memory=False):
  """Runs the benchmarking for a combination of (bazel version, project version).

  Args:
    bazel_binary_path: the path to the bazel binary to be run.
    command: the command to be run with Bazel.
    expressions: the list of command-specific expressions.
    options: the list of non-startup options.
    bazelrc: the path to a .bazelrc file.
    collect_memory: whether the benchmarking should collect memory info.

  Returns:
    A result object:
    {
      'wall': 1.000,
      'cpu': 1.000,
      'system': 1.000,
      'memory': 1.000,
    }
  """
  bazel = Bazel(bazel_binary_path, bazelrc)

  default_arguments = collections.defaultdict(list)

  # Prepend some default options if the command is 'build'.
  # The order in which the options appear matters.
  if command == 'build':
    options_set = set(options)
    default_options = list(
        filter(
            lambda x: x not in options_set,
            ['--nostamp', '--noshow_progress', '--color=no']))
    options = default_options + options

  times = bazel.command(
      command_name=command,
      args=options + expressions,
      collect_memory=collect_memory)

  # Get back to a clean state.
  bazel.command('clean', ['--color=no'])
  bazel.command('shutdown')
  return times


def _run_benchmark(bazel_binary_path,
                   project_path,
                   runs,
                   collect_memory,
                   bazel_args,
                   bazelrc,
                   prefetch_ext_deps,
                   bep_json_dir=None):
  """Runs the benchmarking for a combination of (bazel version, project version).

  Args:
    bazel_binary_path: the path to the bazel binary to be run.
    project_path: the path to the project clone to be built.
    runs: the number of runs.
    collect_memory: whether the benchmarking should collect memory info.
    bazel_args: the unparsed list of arguments to be passed to Bazel binary.
    bazelrc: the path to a .bazelrc file.
    prefetch_ext_deps: whether to do a first non-benchmarked run to fetch the
      external dependencies.
    bep_json_dir: absolute path to the directory to write the build event json
      file to.

  Returns:
    A list of result objects from each _single_run.
  """
  collected = []

  bazel = Bazel(bazel_binary_path, bazelrc)

  # Runs the command once to make sure external dependencies are fetched.
  # If prefetch_ext_deps, run the command with --build_event_json_file to get the
  # command arguments.
  # Else, fall back to manually parsing it from bazel_args.
  if prefetch_ext_deps:
    bep_json_dir = bep_json_dir or DEFAULT_OUT_BASE_PATH
    if not os.path.exists(bep_json_dir):
      os.makedirs(bep_json_dir)
    bep_json_path = bep_json_dir + 'build_env.json'
    os.chdir(project_path)

    logger.log('Pre-fetching external dependencies & exporting build env json ' \
        'to %s...' % bep_json_path)

    command = bazel_args[0]
    command_args = bazel_args[1:]
    # It's important to have --build_event_json_file as the last argument, since
    # we exclude this injected flag when parsing command options by simply
    # discarding the last argument.
    bazel.command(
        command,
        command_args + ['--build_event_json_file=%s' % bep_json_path])
    command, expressions, options = args_parser.parse_bazel_args_from_build_event(bep_json_path)
    # Get back to a clean state.
    bazel.command('clean', ['--color=no'])
    bazel.command('shutdown')
  else:
    logger.log('Parsing arguments from command line...')
    command, expressions, options = args_parser.parse_bazel_args_from_canonical_str(bazel_args)

  for i in range(runs):
    logger.log('Starting benchmark run %s/%s:' % ((i + 1), runs))
    collected.append(
        _single_run(bazel_binary_path, command,
                    expressions, options, bazelrc,
                    collect_memory))

  return collected, (command, expressions, options)


FLAGS = flags.FLAGS
# Flags for the bazel binaries.
flags.DEFINE_list('bazel_commits', ['latest'],
    'The commits at which bazel is built.')
flags.DEFINE_string(
    'bazel_source', 'https://github.com/bazelbuild/bazel.git',
    'Either a path to the local Bazel repo or a https url to a GitHub repository.')

# Flags for the project to be built.
flags.DEFINE_string(
    'project_source', None,
    'Either a path to the local git project to be built or a https url to a GitHub repository.')
flags.DEFINE_list(
    'project_commits', ['latest'],
    'The commits from the git project to be benchmarked.')

# Execution options.
flags.DEFINE_integer('runs', 3, 'The number of benchmark runs.')
flags.DEFINE_string('bazelrc', None, 'The path to a .blazerc file.')

# Miscellaneous flags.
flags.DEFINE_boolean('verbose', False,
                     'Whether to include git/Bazel stdout logs.')
flags.DEFINE_boolean('collect_memory', False,
                     'Whether to collect used heap sizes.')
flags.DEFINE_boolean('prefetch_ext_deps', True,
                     'Whether to do an initial run to pre-fetch external dependencies.')

# Output storage flags.
flags.DEFINE_string(
    'data_directory', None,
    'The directory in which the csv files should be stored (including the trailing "/"), \
    turns on memory collection.')
flags.DEFINE_boolean('upload_data', False,
                     'Whether to upload the result to a remote storage.')


def _flag_checks():
  """Verify flags requirements."""
  if FLAGS.bazel_commits and FLAGS.project_commits \
    and len(FLAGS.bazel_commits) > 1 and len(FLAGS.project_commits) > 1:
    raise ValueError(
        'Either --bazel_commits or --project_commits should be a single element.'
    )
  if FLAGS.upload_data and not os.path.exists('utils/config.py'):
    raise ValueError(
        '--upload_data specified without a present utils/config.py.')


def main(argv):
  _flag_checks()

  # Strip off 'benchmark.py' from argv
  # argv would be something like:
  # ['benchmark.py', 'build', '--nobuild', '//:all']
  bazel_args = argv[1:]

  # Building Bazel binaries
  bazel_binaries = []
  logger.log('Preparing bazelbuild/bazel repository.')
  bazel_source = FLAGS.bazel_source if FLAGS.bazel_source else BAZEL_GITHUB_URL
  bazel_clone_path = _setup_project_repo(BAZEL_CLONE_PATH, bazel_source)

  # Set up project repo
  logger.log('Preparing %s clone.' % FLAGS.project_source)
  project_clone_path = _setup_project_repo(
      PROJECT_CLONE_BASE_PATH + _get_clone_subdir(FLAGS.project_source),
      FLAGS.project_source)

  # A dictionary that maps a (bazel_commit, project_commit) tuple
  # to its benchmarking result.
  data = {}
  csv_data = {}
  for bazel_commit in FLAGS.bazel_commits:
    for project_commit in FLAGS.project_commits:
      bazel_binary_path = _build_bazel_binary(bazel_commit, bazel_clone_path,
                                              BAZEL_BINARY_BASE_PATH)
      _checkout_project_commit(project_commit, project_clone_path)
      results, args = _run_benchmark(bazel_binary_path, project_clone_path,
                               FLAGS.runs, FLAGS.collect_memory or FLAGS.data_directory,
                               bazel_args, FLAGS.bazelrc, FLAGS.prefetch_ext_deps)
      collected = {}
      for benchmarking_result in results:
        for metric, value in benchmarking_result.items():
          if metric not in collected:
            collected[metric] = Values()
          collected[metric].add(value)

      data[(bazel_commit, project_commit)] = collected
      csv_data[(bazel_commit, project_commit)] = {
        'results': results,
        'args': args
      }


  print('\nRESULTS:')
  last_collected = None
  for (bazel_commit, project_commit), collected in sorted(data.items()):
    print('Bazel commit: %s, Project commit: %s, Project source: %s' %
          (bazel_commit, project_commit, FLAGS.project_source))
    for metric, values in sorted(collected.items()):
      if metric == 'exit_status':
        continue
      if last_collected:
        base = last_collected[metric]
        pval = ', pval: % 7.5f' % values.pval(base.values())
        mean_diff = '(% +6.2f%%)' % (100. * (values.mean() - base.mean()) /
                                     base.mean())
        median_diff = '(% +6.2f%%)' % (100. *
                                       (values.median() - base.median()) /
                                       base.median())
      else:
        pval = ''
        mean_diff = median_diff = '         '
      print('% 8s: mean: % 8.3fs %s, median: % 8.3fs %s, stddev: % 7.3f%s' %
            (metric, values.mean(), mean_diff, values.median(), median_diff,
             values.stddev(), pval))
    last_collected = collected

  if FLAGS.data_directory or FLAGS.upload_data:
    data_directory = FLAGS.data_directory or DEFAULT_OUT_BASE_PATH
    csv_file_path = export_csv(data_directory, csv_data, FLAGS.project_source)
    if FLAGS.upload_data:
      upload_csv(csv_file_path)

  logger.log('Done.')


if __name__ == '__main__':
  flags.mark_flag_as_required('project_source')
  app.run(main)
