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
from __future__ import print_function

import os
import subprocess
import hashlib
import re
import shutil
import collections
import tempfile
import git
import utils.logger as logger
import utils.bazel_args_parser as args_parser

from absl import app
from absl import flags
from absl.flags import argparse_flags

from utils.values import Values
from utils.bazel import Bazel
from utils.output_handling import export_csv, upload_csv

# TMP has different values, depending on the platform.
TMP = tempfile.gettempdir()


def _platform_path_str(posix_path):
  """Converts the path to the appropriate format for platform."""
  if os.name == 'nt':
    return posix_path.replace('/', '\\')
  return posix_path


# The path to the cloned bazelbuild/bazel repo.
BAZEL_CLONE_PATH = _platform_path_str('%s/.bazel-bench/bazel' % TMP)
# The path to the clone of the project to be built with Bazel.
PROJECT_CLONE_BASE_PATH = _platform_path_str('%s/.bazel-bench/project-clones/' %
                                             TMP)
BAZEL_GITHUB_URL = 'https://github.com/bazelbuild/bazel.git'
# The path to the directory that stores the bazel binaries.
BAZEL_BINARY_BASE_PATH = _platform_path_str('%s/.bazel-bench/bazel-bin/' % TMP)
# The path to the directory that stores the output csv (If required).
DEFAULT_OUT_BASE_PATH = _platform_path_str('%s/.bazel-bench/out/' % TMP)


def _get_clone_subdir(project_source):
  """Calculates a hexdigest of project_source to serve as a unique subdir name."""
  return hashlib.md5(project_source).hexdigest()


def _exec_command(args, shell=False, fail_if_nonzero=True, cwd=None):
  logger.log('Executing: %s' % ' '.join(args))
  if FLAGS.verbose:
    return subprocess.call(args, shell=shell, cwd=cwd)

  fd_devnull = open(os.devnull, 'w')
  return subprocess.call(
      args, shell=shell, stdout=fd_devnull, stderr=fd_devnull, cwd=cwd)


def _get_commits_topological(commits_sha_list, repo, flag_name):
  """Returns a list of commits, sorted by topological order.

  e.g. for a commit history A -> B -> C -> D, commits_sha_list = [C, B]
  Output: [B, C]

  If the input commits_sha_list is empty, fetch the latest commit on branch
  'master'
  of the repo.

  Args:
    commits_sha_list: a list of string of commit SHA digest.
    repo: the git.Repo instance of the repository.
    flag_name: the flag that is supposed to specify commits_list.

  Returns:
    A list of string of commit SHA digests, sorted by topological commit order.
  """
  if commits_sha_list:
    commits_sha_set = set(commits_sha_list)
    return [
        c.hexsha
        for c in reversed(list(repo.iter_commits()))
        if c.hexsha in commits_sha_set
    ]

  # If no commit specified: take the repo's latest commit.
  latest_commit_sha = repo.commit().hexsha
  logger.log('No %s specified, using the latest one: %s' %
             (flag_name, latest_commit_sha))
  return [latest_commit_sha]


def _setup_project_repo(repo_path, project_source):
  """Returns a path to the cloned repository.

  If the repo_path exists, perform a `git pull` to update the content.
  Else, clone the project to repo_path.

  The cloned repository is guaranteed to be at the latest commit.

  Args:
    repo_path: the path to clone the repository to.
    project_source: the source to clone the repository from. Could be a local
      path or an URL.

  Returns:
    A git.Repo object of the cloned repository.
  """
  if os.path.exists(repo_path):
    logger.log('Path %s exists. Updating...' % repo_path)
    repo = git.Repo(repo_path)
    repo.git.checkout('master')
    repo.git.pull('-f', 'origin', 'master')
  else:
    logger.log('Cloning %s to %s...' % (project_source, repo_path))
    repo = git.Repo.clone_from(project_source, repo_path)

  return repo


def _build_bazel_binary(commit, repo, outroot):
  """Builds bazel at the specified commit and copy the output binary to outroot.

  If the binary for this commit already exists at the destination path, simply
  return the path without re-building.

  Args:
    commit: the Bazel commit SHA.
    repo: the git.Repo instance of the Bazel clone.
    outroot: the directory inwhich the resulting binary is copied to.

  Returns:
    The path to the resulting binary (copied to outroot).
  """
  destination = outroot + commit
  if os.path.exists(destination):
    logger.log('Binary exists at %s, reusing...' % destination)
    return destination

  logger.log('Building Bazel binary at commit %s' % commit)
  repo.git.checkout('-f', commit)

  _exec_command(['bazel', 'build', '//src:bazel'], cwd=repo.working_dir)

  # Copy to another location
  binary_out = '%s/bazel-bin/src/bazel' % repo.working_dir
  destination = outroot + commit

  if not os.path.exists(outroot):
    os.makedirs(outroot)
  logger.log('Copying bazel binary to %s' % destination)
  shutil.copyfile(binary_out, destination)
  _exec_command(['chmod', '+x', destination])

  return destination


def _single_run(bazel_binary_path,
                command,
                args,
                bazelrc=None,
                collect_memory=False):
  """Runs the benchmarking for a combination of (bazel version, project version).

  Args:
    bazel_binary_path: the path to the bazel binary to be run.
    command: the command to be run with Bazel.
    args: the list of arguments (options and expressions) to pass to the Bazel
      command.
    bazelrc: the path to a .bazelrc file.
    collect_memory: whether the benchmarking should collect memory info.

  Returns:
    A result object:
    {
      'wall': 1.000,
      'cpu': 1.000,
      'system': 1.000,
      'memory': 1.000,
      'exit_status': 0,
      'started_at': datetime.datetime(2019, 1, 1, 0, 0, 0, 000000),
    }
  """
  bazel = Bazel(bazel_binary_path, bazelrc)

  default_arguments = collections.defaultdict(list)

  # Prepend some default options if the command is 'build'.
  # The order in which the options appear matters.
  if command == 'build':
    args_set = set(args)
    default_options = list(
        filter(lambda x: x not in args,
               ['--nostamp', '--noshow_progress', '--color=no']))
    args = default_options + args

  measurements = bazel.command(
      command_name=command, args=args, collect_memory=collect_memory)

  # Get back to a clean state.
  bazel.command('clean', ['--color=no'])
  bazel.command('shutdown')
  return measurements


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

    logger.log('Pre-fetching external dependencies & exporting build event json ' \
        'to %s...' % bep_json_path)

    # The command is guaranteed to be the first element since we don't support
    # startup options.
    command = bazel_args[0]

    # It's important to have --build_event_json_file as the last argument, since
    # we exclude this injected flag when parsing command options by simply
    # discarding the last argument.
    command_args = bazel_args[1:] + [
        '--build_event_json_file=%s' % bep_json_path
    ]

    _single_run(bazel_binary_path, command, command_args, bazelrc,
                collect_memory)
    command, expressions, options = args_parser.parse_bazel_args_from_build_event(
        bep_json_path)
  else:
    logger.log('Parsing arguments from command line...')
    command, expressions, options = args_parser.parse_bazel_args_from_canonical_str(
        bazel_args)

  parsed_args = options + expressions
  for i in range(runs):
    logger.log('Starting benchmark run %s/%s:' % ((i + 1), runs))
    collected.append(
        _single_run(bazel_binary_path, command, parsed_args, bazelrc,
                    collect_memory))

  return collected, (command, expressions, options)


FLAGS = flags.FLAGS
# Flags for the bazel binaries.
flags.DEFINE_list('bazel_commits', None, 'The commits at which bazel is built.')
flags.DEFINE_string('bazel_source',
                    'https://github.com/bazelbuild/bazel.git',
                    'Either a path to the local Bazel repo or a https url to ' \
                    'a GitHub repository.')

# Flags for the project to be built.
flags.DEFINE_string('project_source', None,
                    'Either a path to the local git project to be built or ' \
                    'a https url to a GitHub repository.')
flags.DEFINE_list('project_commits', None,
                  'The commits from the git project to be benchmarked.')

# Execution options.
flags.DEFINE_integer('runs', 3, 'The number of benchmark runs.')
flags.DEFINE_string('bazelrc', None, 'The path to a .bazelrc file.')

# Miscellaneous flags.
flags.DEFINE_boolean('verbose', False,
                     'Whether to include git/Bazel stdout logs.')
flags.DEFINE_boolean('collect_memory', False,
                     'Whether to collect used heap sizes.')
flags.DEFINE_boolean('prefetch_ext_deps', True,
                     'Whether to do an initial run to pre-fetch external ' \
                     'dependencies.')

# Output storage flags.
flags.DEFINE_string('data_directory', None,
                    'The directory in which the csv files should be stored ' \
                    '(excluding the trailing "/"). Turns on memory collection.')
flags.DEFINE_string('upload_data_to', None,
                    'The details of the BigQuery table to upload ' \
                    'results to: <dataset_id>:<table_id>:<location>')


def _flag_checks():
  """Verify flags requirements."""
  if (FLAGS.bazel_commits and FLAGS.project_commits and
      len(FLAGS.bazel_commits) > 1 and len(FLAGS.project_commits) > 1):
    raise ValueError(
        'Either --bazel_commits or --project_commits should be a single element.'
    )

  if FLAGS.upload_data_to:
    if not re.match('^[\w-]+:[\w-]+:[\w-]+$', FLAGS.upload_data_to):
      raise ValueError('--upload_data_to should follow the pattern '
                       '<dataset_id>:<table_id>:<location>')

    if ('GOOGLE_APPLICATION_CREDENTIALS' not in os.environ or
        not os.environ['GOOGLE_APPLICATION_CREDENTIALS']):
      raise ValueError('GOOGLE_APPLICATION_CREDENTIALS is required to '
                       'upload data to bigquery.')


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
  bazel_clone_repo = _setup_project_repo(BAZEL_CLONE_PATH, bazel_source)

  bazel_commits = _get_commits_topological(FLAGS.bazel_commits,
                                           bazel_clone_repo, 'bazel_commits')

  # Set up project repo
  logger.log('Preparing %s clone.' % FLAGS.project_source)
  project_clone_repo = _setup_project_repo(
      PROJECT_CLONE_BASE_PATH + _get_clone_subdir(FLAGS.project_source),
      FLAGS.project_source)

  project_commits = _get_commits_topological(FLAGS.project_commits,
                                             project_clone_repo,
                                             'project_commits')

  # A dictionary that maps a (bazel_commit, project_commit) tuple
  # to its benchmarking result.
  data = {}
  csv_data = {}

  for bazel_commit in bazel_commits:
    for project_commit in project_commits:
      bazel_binary_path = _build_bazel_binary(bazel_commit, bazel_clone_repo,
                                              BAZEL_BINARY_BASE_PATH)
      project_clone_repo.git.checkout('-f', project_commit)

      results, args = _run_benchmark(
          bazel_binary_path, project_clone_repo.working_dir, FLAGS.runs,
          FLAGS.collect_memory or FLAGS.data_directory, bazel_args,
          FLAGS.bazelrc, FLAGS.prefetch_ext_deps)
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
  for (bazel_commit, project_commit), collected in data.items():
    print('Bazel commit: %s, Project commit: %s, Project source: %s' %
          (bazel_commit, project_commit, FLAGS.project_source))
    for metric, values in collected.items():
      if metric in ['exit_status', 'started_at']:
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

  if FLAGS.data_directory or FLAGS.upload_data_to:
    data_directory = FLAGS.data_directory or DEFAULT_OUT_BASE_PATH
    csv_file_path = export_csv(data_directory, csv_data, FLAGS.project_source)
    if FLAGS.upload_data_to:
      upload_csv(csv_file_path, FLAGS.upload_data_to)

  logger.log('Done.')


if __name__ == '__main__':
  flags.mark_flag_as_required('project_source')
  app.run(main)
