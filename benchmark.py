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
import csv
import collections
import datetime
import os
import subprocess
import sys
import hashlib
import re
import shutil
import collections
import tempfile
import math
import git
import utils.logger as logger
import utils.json_profiles_merger_lib as json_profiles_merger_lib
import utils.output_handling as output_handling
import utils.bep as bep
import utils.patch as patch_util
import utils.bisection as bisection

from absl import app
from absl import flags

from utils.values import Values
from utils.bazel import Bazel
from utils.benchmark_config import BenchmarkConfig

# BB_ROOT has different values, depending on the platform.
BB_ROOT = os.path.join(os.path.expanduser('~'), '.bazel-bench')

# The path to the directory that stores Bazel clones.
BAZEL_CLONE_BASE_PATH = os.path.join(BB_ROOT, 'bazel-clones')
# The path to the directory that stores project clones.
PROJECT_CLONE_BASE_PATH = os.path.join(BB_ROOT, 'project-clones')
BAZEL_GITHUB_URL = 'https://github.com/bazelbuild/bazel.git'
# The path to the directory that stores the bazel binaries.
BAZEL_BINARY_BASE_PATH = os.path.join(BB_ROOT, 'bazel-bin')
# The default name of the aggr json profile.
DEFAULT_AGGR_JSON_PROFILE_FILENAME = 'aggr_json_profiles.csv'


def _get_clone_subdir(project_source):
  """Calculates a hexdigest of project_source to serve as a unique subdir name."""
  return hashlib.md5(project_source.encode('utf-8')).hexdigest()


def _resolve_path(path):
  """Resolves a filesystem path against BUILD_WORKING_DIRECTORY or cwd if not a URL."""
  if not path:
    return path
  if path.startswith(('http://', 'https://', 'git@', 'ssh://', 'file://')):
    return path
  base_dir = os.environ.get('BUILD_WORKING_DIRECTORY', os.getcwd())
  return os.path.abspath(os.path.join(base_dir, os.path.expanduser(path)))


def _get_local_project_commit(project_source):
  """Gets the HEAD commit SHA for a local project, or 'local' if unavailable."""
  if project_source and (os.path.isdir(os.path.join(project_source, '.git')) or
                         os.path.isfile(os.path.join(project_source, '.git'))):
    try:
      out = subprocess.check_output(
          ['git', 'rev-parse', 'HEAD'],
          cwd=project_source,
          stderr=subprocess.DEVNULL,
          text=True).strip()
      if out:
        return out
    except Exception:
      pass
    try:
      local_repo = git.Repo(project_source)
      return local_repo.head.commit.hexsha
    except Exception:
      pass
  return 'local'


def _check_no_patch_in_place(project_source, patch_files):
  """Refuses patch files when benchmarking a local project in place.

  The patch is applied to and reverted from the project tree around every run.
  Doing that in the user's own checkout is risky: if the benchmark is
  interrupted, or the user edits a patched file meanwhile, the checkout is left
  modified (or the revert fails).
  """
  if any(patch_files):
    raise ValueError(
        '--patch_file/patch_file cannot be used when benchmarking %s in place: '
        'the patch would be repeatedly applied to and reverted from your own '
        'checkout. Pass --project_commits (or project_commit in the config) so '
        'the project is cloned.' % project_source)


def _exec_command(args, shell=False, cwd=None):
  logger.log('Executing: %s' % (args if shell else ' '.join(args)))

  return subprocess.run(
      args,
      shell=shell,
      cwd=cwd,
      check=True,
      stdout=sys.stdout if FLAGS.verbose else subprocess.DEVNULL,
      stderr=sys.stderr if FLAGS.verbose else subprocess.DEVNULL)


def _get_commits_topological(commits_sha_list,
                             repo,
                             flag_name,
                             fill_default=True):
  """Returns a list of commits, sorted by topological order.

  e.g. for a commit history A -> B -> C -> D, commits_sha_list = [C, B]
  Output: [B, C]

  If the input commits_sha_list is empty, fetch the latest commit on branch
  'master'
  of the repo.

  Args:
    commits_sha_list: a list of string of commit SHA digest. Can be long or
      short digest.
    repo: the git.Repo instance of the repository.
    flag_name: the flag that is supposed to specify commits_list.
    fill_default: whether to fill in a default latest commit if none is
      specified.

  Returns:
    A list of string of full SHA digests, sorted by topological commit order.
  """
  if commits_sha_list:
    long_commits_sha_set = set(
        map(lambda x: _to_long_sha_digest(x, repo), commits_sha_list))
    sorted_commit_list = []
    for c in reversed(list(repo.iter_commits())):
      if c.hexsha in long_commits_sha_set:
        sorted_commit_list.append(c.hexsha)

    if len(sorted_commit_list) != len(long_commits_sha_set):
      raise ValueError(
          "The following commits weren't found in the repo in branch master: %s."
          % (long_commits_sha_set - set(sorted_commit_list)))
    return sorted_commit_list

  elif not fill_default:
    # If we have some binary paths specified, we don't need to fill in a default
    # commit.
    return []

  # If no commit specified: take the repo's latest commit.
  latest_commit_sha = repo.commit().hexsha
  logger.log('No %s specified, using the latest one: %s' %
             (flag_name, latest_commit_sha))
  return [latest_commit_sha]


def _to_long_sha_digest(digest, repo):
  """Returns the full 40-char SHA digest of a commit."""
  return repo.git.rev_parse(digest) if len(digest) < 40 else digest


def _setup_project_repo(repo_path, project_source):
  """Returns a path to the cloned repository.

  If the repo_path exists, perform a `git fetch` to update the content.
  Else, clone the project to repo_path.

  Args:
    repo_path: the path to clone the repository to.
    project_source: the source to clone the repository from. Could be a local
      path or an URL.

  Returns:
    A git.Repo object of the cloned repository.
  """
  if os.path.exists(repo_path):
    try:
      repo = git.Repo(repo_path)
      logger.log('Path %s exists. Updating...' % repo_path)
      repo.git.fetch('origin')
      return repo
    except Exception:
      logger.log('Path %s exists but is not a valid git repository. Re-cloning...' % repo_path)
      shutil.rmtree(repo_path, ignore_errors=True)

  logger.log('Cloning %s to %s...' % (project_source, repo_path))
  try:
    subprocess.run(['git', 'clone', '--ref-format=files', project_source, repo_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    repo = git.Repo(repo_path)
  except Exception:
    repo = git.Repo.clone_from(project_source, repo_path)

  return repo


def _build_bazel_binary(commit, repo, outroot, platform=None):
  """Builds bazel at the specified commit and copy the output binary to outroot.

  If the binary for this commit already exists at the destination path, simply
  return the path without re-building.

  Args:
    commit: the Bazel commit SHA.
    repo: the git.Repo instance of the Bazel clone.
    outroot: the directory inwhich the resulting binary is copied to.
    platform: the platform on which to build this binary.

  Returns:
    The path to the resulting binary (copied to outroot).
  """
  outroot_for_commit = '%s/%s/%s' % (
      outroot, platform, commit) if platform else '%s/%s' % (outroot, commit)
  destination = '%s/bazel' % outroot_for_commit
  if os.path.exists(destination):
    logger.log('Binary exists at %s, reusing...' % destination)
    return destination

  logger.log('Building Bazel binary at commit %s' % commit)
  repo.git.checkout('-f', commit)

  _exec_command(['bazel', 'build', '//src:bazel'], cwd=repo.working_dir)

  # Copy to another location
  binary_out = '%s/bazel-bin/src/bazel' % repo.working_dir

  if not os.path.exists(outroot_for_commit):
    os.makedirs(outroot_for_commit)
  logger.log('Copying bazel binary to %s' % destination)
  shutil.copyfile(binary_out, destination)
  _exec_command(['chmod', '+x', destination])

  return destination


def _construct_json_profile_flags(out_file_path):
  """Constructs the flags used to collect JSON profiles.

  Args:
    out_file_path: The path to output the profile to.

  Returns:
    A list of string representing the flags.
  """
  return [
      '--experimental_generate_json_trace_profile',
      '--profile={}'.format(out_file_path)
  ]


def json_profile_filename(data_directory, bazel_bench_uid, bazel_commit,
                          unit_num, project_commit, run_number, total_runs):
  return (f'{data_directory}/{bazel_bench_uid}_{bazel_commit}_{unit_num}'
          + f'_{project_commit}_{run_number}_of_{total_runs}.profile.gz')


def format_float_map(m):
  """Formats a metrics dict compactly, e.g. {wall: 0.224s, cpu: 20.74s}."""
  parts = []
  unit_map = {
      'wall': 's',
      'cpu': 's',
      'system': 's',
      'memory': 'MB',
      'peakProcessRss': 'MB',
      'postGcProcessRss': 'MB',
      'peakPostGcHeapSize': 'MB',
      'usedHeapSizePostBuild': 'MB',
      'edenSpaceGarbage': 'MB',
      'oldGenGarbage': 'MB',
  }
  for k, v in m.items():
    if k in ['exit_status', 'invocation_id', 'started_at']:
      parts.append(f'{k}: {v}')
    elif isinstance(v, int):
      parts.append(f'{k}: {v:,}')
    elif isinstance(v, float):
      u = unit_map.get(k, '')
      parts.append(f'{k}: {v:.3f}{u}')
    else:
      parts.append(f'{k}: {v}')
  return '{' + ', '.join(parts) + '}'


def _single_run(bazel_bin_path,
                command,
                options,
                targets,
                startup_options,
                collect_memory=True,
                collect_process_memory=False):
  """Runs the benchmarking for a combination of (bazel version, project version).

  Args:
    bazel_bin_path: the path to the bazel binary to be run.
    command: the command to be run with Bazel.
    options: the list of options.
    targets: the list of targets.
    startup_options: the list of target options.
    collect_memory: whether to collect retained heap size via GC.
    collect_process_memory: whether to sample peak process RSS.

  Returns:
    A result object with collected metrics.
  """
  bazel = Bazel(bazel_bin_path, startup_options)


  # Prepend some default options if the command is 'build'.
  # The order in which the options appear matters.
  if command == 'build':
    options = options + ['--nostamp', '--noshow_progress', '--color=no']
  measurements = bazel.command(
      command,
      args=options + targets,
      collect_memory=collect_memory,
      collect_process_memory=collect_process_memory)

  if measurements is not None:
    command_failed = measurements.get('exit_status', 0) != 0
    logger.log('Single run done, results: %s' % format_float_map(measurements), warning=command_failed)

  if FLAGS.clean:
    bazel.command('clean', ['--color=no'])

  if FLAGS.shutdown:
    bazel.command('shutdown')

  return measurements


def _run_single_benchmark_iteration(bazel_bin_path,
                                    command,
                                    options,
                                    targets,
                                    startup_options,
                                    run_number,
                                    total_runs,
                                    unit_num=0,
                                    bazel_bench_uid=None,
                                    data_directory=None,
                                    collect_profile=False,
                                    bazel_identifier=None,
                                    project_commit=None,
                                    collect_memory=True,
                                    collect_process_memory=False,
                                    collect_bep=False):
  """Executes a single benchmark iteration, including profiling and BEP ingestion."""
  maybe_include_flags = options[:]
  bep_file_path = None
  if collect_bep:
    bep_dir = data_directory or tempfile.gettempdir()
    if not os.path.exists(bep_dir):
      os.makedirs(bep_dir)
    bep_file_path = os.path.join(
        bep_dir, f'{bazel_bench_uid}_{unit_num}_{run_number}_bep.json')
    maybe_include_flags += bep.get_bep_flags(bep_file_path)

  if collect_profile:
    assert bazel_identifier, ('bazel_identifier is required when '
                              'collect_profile')
    assert project_commit, ('project_commit is required when '
                            'collect_profile')
    maybe_include_flags += _construct_json_profile_flags(
        json_profile_filename(
            data_directory=data_directory,
            bazel_bench_uid=bazel_bench_uid,
            bazel_commit=bazel_identifier.replace('/', '_'),
            unit_num=unit_num,
            project_commit=project_commit,
            run_number=run_number,
            total_runs=total_runs,
        ))

  run_result = _single_run(
      bazel_bin_path,
      command,
      maybe_include_flags,
      targets,
      startup_options,
      collect_memory=collect_memory,
      collect_process_memory=collect_process_memory)

  if run_result is not None and collect_bep and bep_file_path and os.path.exists(bep_file_path):
    bep_data = bep.parse_bep_json_file(bep_file_path)
    for k, v in bep_data.items():
      if isinstance(v, (int, float)) and not math.isnan(v):
        run_result[k] = v
      elif k == 'invocation_id':
        run_result['invocation_id'] = v

  return run_result


def _run_benchmark(bazel_bin_path,
                   project_path,
                   runs,
                   command,
                   options,
                   targets,
                   startup_options,
                   prefetch_ext_deps,
                   bazel_bench_uid,
                   unit_num,
                   data_directory=None,
                   collect_profile=False,
                   bazel_identifier=None,
                   project_commit=None,
                   warmup_runs=0,
                   max_outlier_reruns=0,
                   collect_memory=True,
                   collect_process_memory=False,
                   collect_bep=False,
                   patch_file=None):
  """Runs the benchmarking for a combination of (bazel version, project version).

  Args:
    bazel_bin_path: the path to the bazel binary to be run.
    project_path: the path to the project clone to be built.
    runs: the number of runs.
    command: the Bazel command (e.g. build).
    options: options for the Bazel command.
    targets: targets for the Bazel command.
    startup_options: startup options for Bazel.
    prefetch_ext_deps: whether to do a first non-benchmarked run to fetch external deps.
    bazel_bench_uid: a unique string identifier of this entire bazel-bench run.
    unit_num: the numerical order of the current unit being benchmarked.
    data_directory: the path to the directory to store run data. Required if collect_profile.
    collect_profile: whether to collect JSON profile for each run.
    bazel_identifier: the commit hash or binary path of the bazel version.
    project_commit: the commit hash of the project commit.
    warmup_runs: number of initial warmup runs to perform (discarded).
    max_outlier_reruns: maximum number of automatic reruns when a wall-time outlier is detected.
    collect_memory: whether to collect retained heap size via GC.
    collect_process_memory: whether to sample peak anonymous process RSS.
    collect_bep: whether to collect build metrics from BEP.
    patch_file: path to a patch file containing changes to apply for incremental rebuilds.

  Returns:
    A list of result objects from each _single_run.
  """
  collected = []
  os.chdir(project_path)

  logger.log('=== BENCHMARKING BAZEL [Unit #%d]: %s, PROJECT: %s ===' %
             (unit_num, bazel_identifier, project_commit))
  # Runs the command once to make sure external dependencies are fetched.
  if prefetch_ext_deps:
    logger.log('Pre-fetching external dependencies...')
    _single_run(bazel_bin_path, command, options, targets, startup_options)

  if warmup_runs > 0:
    for w in range(1, warmup_runs + 1):
      logger.log('Starting warmup run %d/%d:' % (w, warmup_runs))
      with patch_util.apply_patch(project_path, patch_file):
        _single_run(bazel_bin_path, command, options, targets, startup_options)

  if collect_profile:
    if not os.path.exists(data_directory):
      os.makedirs(data_directory)

  for i in range(1, runs + 1):
    logger.log('Starting benchmark run %s/%s:' % (i, runs))
    with patch_util.apply_patch(project_path, patch_file):
      run_result = _run_single_benchmark_iteration(
          bazel_bin_path=bazel_bin_path,
          command=command,
          options=options,
          targets=targets,
          startup_options=startup_options,
          run_number=i,
          total_runs=runs,
          unit_num=unit_num,
          bazel_bench_uid=bazel_bench_uid,
          data_directory=data_directory,
          collect_profile=collect_profile,
          bazel_identifier=bazel_identifier,
          project_commit=project_commit,
          collect_memory=collect_memory or FLAGS.collect_memory,
          collect_process_memory=collect_process_memory or FLAGS.collect_process_memory,
          collect_bep=collect_bep or FLAGS.collect_bep)
    collected.append(run_result)

  if max_outlier_reruns > 0:
    reruns_left = max_outlier_reruns
    reruns_performed = 0
    while reruns_left > 0:
      valid_indices = [
          idx for idx, r in enumerate(collected)
          if r and 'wall' in r and r.get('exit_status', 0) == 0
      ]
      wall_vals = Values([collected[idx]['wall'] for idx in valid_indices])
      outliers = wall_vals.get_outlier_indices()
      if not outliers:
        break
      med = wall_vals.median()
      worst_subidx = max(outliers, key=lambda idx: abs(wall_vals.values()[idx] - med))
      worst_idx = valid_indices[worst_subidx]
      logger.log(
          'Detected wall-time outlier (%.3fs). Performing outlier rerun (%d remaining)...'
          % (wall_vals.values()[worst_subidx], reruns_left))
      reruns_left -= 1
      reruns_performed += 1
      del collected[worst_idx]
      with patch_util.apply_patch(project_path, patch_file):
        rerun_res = _run_single_benchmark_iteration(
            bazel_bin_path=bazel_bin_path,
            command=command,
            options=options,
            targets=targets,
            startup_options=startup_options,
            run_number=runs + reruns_performed,
            total_runs=runs,
            unit_num=unit_num,
            bazel_bench_uid=bazel_bench_uid,
            data_directory=data_directory,
            collect_profile=collect_profile,
            bazel_identifier=bazel_identifier,
            project_commit=project_commit,
            collect_memory=collect_memory or FLAGS.collect_memory,
            collect_process_memory=collect_process_memory or FLAGS.collect_process_memory,
            collect_bep=collect_bep or FLAGS.collect_bep)
      collected.append(rerun_res)

  return collected, (command, targets, options)


def handle_json_profiles_aggr(bazel_bench_uid, unit_num, bazel_commits,
                              project_source, project_commits, runs,
                              output_path, data_directory):
  """Aggregates the collected JSON profiles and writes the result to a CSV.

   Args:
    bazel_bench_uid: a unique string identifier of this entire bazel-bench run.
    unit_num: the numerical order of the current unit being benchmarked.
    bazel_commits: the Bazel commits that bazel-bench ran on.
    project_source: a path/url to a local/remote repository of the project on
      which benchmarking was performed.
    project_commits: the commits of the project when benchmarking was done.
    runs: the total number of runs.
    output_path: the path to the output csv file.
    data_directory: the directory that stores output files.
  """
  output_dir = os.path.dirname(output_path)
  if not os.path.exists(output_dir):
    os.makedirs(output_dir)

  with open(output_path, 'w') as f:
    csv_writer = csv.writer(f)
    csv_writer.writerow([
        'bazel_source', 'project_source', 'project_commit', 'cat', 'name', 'dur'
    ])

    for bazel_commit in bazel_commits:
      for project_commit in project_commits:
        profiles_filenames = [
            json_profile_filename(
                data_directory=data_directory,
                bazel_bench_uid=bazel_bench_uid,
                bazel_commit=bazel_commit,
                unit_num=unit_num,
                project_commit=project_commit,
                run_number=i,
                total_runs=runs,
            )
            for i in range(1, runs + 1)
        ]
        event_list = json_profiles_merger_lib.aggregate_data(
            profiles_filenames, only_phases=True)
        for event in event_list:
          csv_writer.writerow([
              bazel_commit, project_source, project_commit, event['cat'],
              event['name'], event['median']
          ])
  logger.log('Finished writing aggregate_json_profiles to %s' % output_path)


def _metric_sort_key(metric_name):
  primary = ('wall', 'cpu', 'system', 'memory')
  if metric_name in primary:
    return (0, primary.index(metric_name))
  elif metric_name.startswith('runner-'):
    return (3, metric_name)
  elif metric_name in (
      'edenSpaceGarbage',
      'oldGenGarbage',
      'peakPostGcHeapSize',
      'usedHeapSizePostBuild',
      'peakProcessRss',
      'postGcProcessRss',
  ):
    return (2, metric_name)
  else:
    return (1, metric_name)


_NON_NUMERIC_METRICS = ('exit_status', 'started_at', 'invocation_id')


def _non_zero_runs(collected):
  """Returns a map from run index to exit code for runs that failed."""
  non_zero_runs = {}
  if 'exit_status' in collected:
    for run_idx, exit_code in enumerate(collected['exit_status'].items()):
      if exit_code != 0:
        non_zero_runs[run_idx] = exit_code
  return non_zero_runs


def _collect_metrics(results):
  """Aggregates a list of per-run result dicts into a map metric -> Values.

  Every metric gets exactly one entry per run, in run order: runs that did not
  report a metric get NaN (or None for non-numeric fields). This keeps run
  indexes aligned across metrics, which is required to correctly exclude
  failed runs by index.
  """
  results = [r for r in results if r is not None]
  metrics = []
  for r in results:
    for metric in r:
      if metric not in metrics:
        metrics.append(metric)
  collected = {}
  for metric in metrics:
    missing = None if metric in _NON_NUMERIC_METRICS else math.nan
    collected[metric] = Values([r.get(metric, missing) for r in results])
  return collected


def create_summary(data, project_source, color=False):
  """Creates the runs summary.

  Excludes runs with non-zero exit codes from the final summary table. Every
  unit is compared against the first unit (the baseline).

  Args:
    data: OrderedDict mapping (unit_num, bazel_identifier, project_commit) to a
      map metric -> Values.
    project_source: the project source, for display.
    color: whether to emit ANSI styling (only for terminal output).
  """
  unit_map = {
      'wall': 's',
      'cpu': 's',
      'system': 's',
      'memory': 'MB',
      'peakProcessRss': 'MB',
      'postGcProcessRss': 'MB',
      'peakPostGcHeapSize': 'MB',
      'usedHeapSizePostBuild': 'MB',
      'edenSpaceGarbage': 'MB',
      'oldGenGarbage': 'MB',
      'analysisPhaseTime': 's',
      'executionPhaseTime': 's',
  }

  def _fmt_val(metric, val):
    if not math.isfinite(val):
      return str(val)
    u = unit_map.get(metric, '')
    if metric in ['wall', 'cpu', 'system', 'analysisPhaseTime', 'executionPhaseTime']:
      return f'{val:.3f}{u}'
    elif metric in ['memory', 'peakProcessRss', 'postGcProcessRss', 'peakPostGcHeapSize', 'usedHeapSizePostBuild', 'edenSpaceGarbage', 'oldGenGarbage']:
      return f'{val:.1f}{u}'
    elif isinstance(val, (int, float)) and val == int(val):
      return f'{int(val):,}{u}'
    return f'{val:.2f}{u}'

  def _fmt_std(metric, std):
    if math.isnan(std):
      return ''
    u = unit_map.get(metric, '')
    if metric in ['wall', 'cpu', 'system', 'analysisPhaseTime', 'executionPhaseTime']:
      return f'±{std:.3f}{u}'
    elif metric in ['memory', 'peakProcessRss', 'postGcProcessRss', 'peakPostGcHeapSize', 'usedHeapSizePostBuild', 'edenSpaceGarbage', 'oldGenGarbage']:
      return f'±{std:.1f}{u}'
    return f'±{std:.1f}{u}'

  # All comparisons are against the first unit (the baseline) and are based on
  # the mean, consistent with the Markdown and JSON reports.
  headers = ['metric', 'mean', '±stddev', 'Δ mean', 'speedup [significance]']
  all_rows = [headers]
  unit_blocks = []
  baseline_collected = None

  for (i, bazel_commit, project_commit), collected in data.items():
    header = ('[Unit #%d] Bazel version: %s, Project commit: %s, Project source: %s' %
              (i, bazel_commit, project_commit, project_source))
    if baseline_collected is None:
      header += ' (baseline)'
    num_runs = len(collected['wall'].items()) if 'wall' in collected else 0
    non_zero_runs = _non_zero_runs(collected)

    rows = []
    filtered_collected = {}
    for metric, values in collected.items():
      if metric in _NON_NUMERIC_METRICS:
        continue
      values_exclude_failures = values.exclude_from_indexes(non_zero_runs.keys())
      if not values_exclude_failures.values_wo_nan():
        continue
      if metric.startswith('runner-') and all(
          v == 0 for v in values_exclude_failures.values_wo_nan()):
        continue
      filtered_collected[metric] = values_exclude_failures

    sorted_metrics = sorted(filtered_collected.keys(), key=_metric_sort_key)

    for metric in sorted_metrics:
      vals = filtered_collected[metric]
      mean_str = _fmt_val(metric, vals.mean())
      std_str = _fmt_std(metric, vals.stddev())

      if baseline_collected is not None and metric in baseline_collected:
        base = baseline_collected[metric]
        if not vals.is_unchanged(base):
          diff = vals.mean() - base.mean()
          diff_str = _fmt_val(metric, diff) if diff <= 0 else f'+{_fmt_val(metric, diff)}'
          ratio, ratio_err, pct = vals.speedup_ratio(base)
          if math.isnan(pct):
            delta_str = diff_str
          else:
            delta_str = f'{diff_str}, {pct:+.1f}%'

          sig = vals.significance_label(base.values())
          if not math.isnan(ratio):
            if ratio_err > 0.0:
              speedup_str = f'{ratio:.2f} ± {ratio_err:.2f}x [{sig}]'
            else:
              speedup_str = f'{ratio:.2f}x [{sig}]'
          else:
            speedup_str = f'[{sig}]'
        else:
          delta_str = ''
          speedup_str = ''
      else:
        delta_str = ''
        speedup_str = ''

      row = [f'{metric}:', mean_str, std_str, delta_str, speedup_str]
      rows.append(row)
      all_rows.append(row)

    if baseline_collected is None:
      baseline_collected = filtered_collected
    unit_blocks.append((header, rows, non_zero_runs, num_runs))

  max_widths = [max(len(cell) for cell in col) for col in zip(*all_rows)]

  summary_builder = ['\nRESULTS:']
  for header, rows, non_zero_runs, num_runs in unit_blocks:
    if color:
      summary_builder.append(f'\033[1m{header}\033[0m')
    else:
      summary_builder.append(header)

    h_line = f"{headers[0].ljust(max_widths[0])}  {headers[1].rjust(max_widths[1])}  {headers[2].rjust(max_widths[2])}  {headers[3].center(max_widths[3])}  {headers[4].ljust(max_widths[4])}".rstrip()
    summary_builder.append(h_line)

    for row in rows:
      line = f"{row[0].ljust(max_widths[0])}  {row[1].rjust(max_widths[1])}  {row[2].rjust(max_widths[2])}  {row[3].center(max_widths[3])}  {row[4].ljust(max_widths[4])}".rstrip()
      summary_builder.append(line)

    if non_zero_runs:
      summary_builder.append(
          ('The following runs contain non-zero exit code(s):\n %s\n'
           'Please check the full log for more details. These runs are '
           'excluded from the above result table.' %
           '\n '.join('- run: %s/%s, exit_code: %s' % (k + 1, num_runs, v)
                      for k, v in non_zero_runs.items())))
    summary_builder.append('')

  return '\n'.join(summary_builder)


FLAGS = flags.FLAGS
# Flags for the bazel binaries.
flags.DEFINE_list('bazel_commits', None, 'The commits at which bazel is built.')
flags.DEFINE_list('bazel_binaries', None,
                  'The pre-built bazel binaries to benchmark.')
flags.DEFINE_string('bazel_source',
                    'https://github.com/bazelbuild/bazel.git',
                    'Either a path to the local Bazel repo or a https url to ' \
                    'a GitHub repository.')
flags.DEFINE_string(
    'bazel_bin_dir', None,
    'The directory to store the bazel binaries from each commit.')

# Flags for the project to be built.
flags.DEFINE_string(
    'project_label', None,
    'The label of the project. Only relevant in the daily performance report.')
flags.DEFINE_string('project_source', None,
                    'Either a path to the local git project to be built or ' \
                    'a https url to a GitHub repository.')
flags.DEFINE_list('project_commits', None,
                  'The commits from the git project to be benchmarked.')
flags.DEFINE_string(
    'env_configure', None,
    "The shell commands to configure the project's environment.")

# Execution options.
flags.DEFINE_integer('runs', 5, 'The number of benchmark runs.')
flags.DEFINE_string('bazelrc', None, 'The path to a .bazelrc file.')
flags.DEFINE_string('platform', None,
                    ('The platform on which bazel-bench is run. This is just '
                     'to categorize data and has no impact on the actual '
                     'script execution.'))
flags.DEFINE_boolean('clean', True, 'Whether to invoke clean between runs/builds.')
flags.DEFINE_boolean('shutdown', True, 'Whether to invoke shutdown between runs/builds.')
flags.DEFINE_boolean('collect_memory', True,
                     'Whether to collect retained heap size via GC after command execution.')
flags.DEFINE_boolean('collect_process_memory', False,
                     'Whether to sample peak anonymous process RSS memory.')
flags.DEFINE_boolean('collect_bep', False,
                     'Whether to collect build metrics from the Build Event Protocol (BEP).')
flags.DEFINE_integer('warmup_runs', 1,
                     'The number of warmup runs to perform before measurements (discarded).')
flags.DEFINE_integer('max_outlier_reruns', 0,
                     'Maximum number of automatic reruns when a wall-time outlier is detected.')
flags.DEFINE_boolean('interleave', False,
                     'Whether to interleave benchmark runs across units in a round-robin order.')
flags.DEFINE_string('patch_file', None,
                    'Path to a patch file containing changes to apply for incremental builds.')

# Miscellaneous flags.
flags.DEFINE_boolean('verbose', False,
                     'Whether to include git/Bazel stdout logs.')
flags.DEFINE_boolean('prefetch_ext_deps', True,
                     'Whether to do an initial run to pre-fetch external ' \
                     'dependencies.')
flags.DEFINE_boolean('collect_profile', False,
                     'Whether to collect JSON profile for each run. Requires ' \
                     '--data_directory to be set.')
flags.DEFINE_boolean('aggregate_json_profiles', False,
                     'Whether to aggregate the collected JSON profiles. Requires '\
                     '--collect_profile to be set.')
flags.DEFINE_string(
    'benchmark_config', None,
    'Whether to use the config-file interface to define benchmark units.')

# Output storage flags.
flags.DEFINE_string('data_directory', None,
                    'The directory in which the csv files should be stored.')
# The daily report generation process on BazelCI requires the csv file name to
# be determined before bazel-bench is launched, so that METADATA files are
# properly filled.
flags.DEFINE_string('csv_file_name', None,
                    'The name of the output csv, without the .csv extension.')
flags.DEFINE_string('bisect', None,
                    'Run automated git bisection for regressions on the specified metric '
                    '(e.g. wall, cpu, memory). Requires --bazel_commits with exactly two commits [good, bad].')


def _flag_checks():
  """Verify flags requirements."""
  if FLAGS.bisect:
    if not FLAGS.bazel_commits or len(FLAGS.bazel_commits) != 2:
      raise ValueError('--bisect requires --bazel_commits with exactly two commits (good bad).')

  if FLAGS.bazel_binaries:
    for b in FLAGS.bazel_binaries:
      resolved_b = _resolve_path(b)
      if not os.path.exists(resolved_b):
        raise ValueError("Bazel binary '%s' does not exist." % b)
      if not os.path.isfile(resolved_b):
        raise ValueError("Bazel binary '%s' is not a regular file." % b)
      if not os.access(resolved_b, os.X_OK):
        raise ValueError("Bazel binary '%s' is not executable (permission denied)." % b)

  if (not FLAGS.benchmark_config and FLAGS.bazel_commits and
      FLAGS.project_commits and len(FLAGS.bazel_commits) > 1 and
      len(FLAGS.project_commits) > 1):
    raise ValueError(
        'Either --bazel_commits or --project_commits should be a single element.'
    )

  if FLAGS.aggregate_json_profiles and not FLAGS.collect_profile:
    raise ValueError('--aggregate_json_profiles requires '
                     '--collect_profile to be set.')


def _get_benchmark_config_and_clone_repos(argv):
  """From the flags/config file, get the benchmark units.

  Args:
    argv: the command line arguments.

  Returns:
    An instance of BenchmarkConfig that contains the benchmark units.
  """
  if FLAGS.benchmark_config:
    config = BenchmarkConfig.from_file(_resolve_path(FLAGS.benchmark_config))
    project_source = _resolve_path(config.get_project_source())
    need_project_clone = not os.path.isdir(project_source) or any(
        'project_commit' in u for u in config.get_units())
    project_clone_repo = None
    if need_project_clone:
      logger.log('Preparing %s clone.' % project_source)
      project_clone_repo = _setup_project_repo(
          PROJECT_CLONE_BASE_PATH + '/' + _get_clone_subdir(project_source),
          project_source)
    else:
      _check_no_patch_in_place(
          project_source,
          [FLAGS.patch_file] + [u.get('patch_file') for u in config.get_units()])
      latest_commit_sha = _get_local_project_commit(project_source)
      for u in config.get_units():
        if 'project_commit' not in u:
          u['project_commit'] = latest_commit_sha
      for u in config._units:
        if 'project_commit' not in u:
          u['project_commit'] = latest_commit_sha

    need_bazel_repo = any('bazel_commit' in u for u in config.get_units()) or bool(FLAGS.bisect)
    bazel_clone_repo = None
    if need_bazel_repo:
      logger.log('Preparing bazelbuild/bazel repository.')
      bazel_source = _resolve_path(config.get_bazel_source())
      bazel_clone_repo = _setup_project_repo(
          BAZEL_CLONE_BASE_PATH + '/' + _get_clone_subdir(bazel_source),
          bazel_source)

    return config, bazel_clone_repo, project_clone_repo

  # Strip off 'benchmark.py' from argv
  # argv would be something like:
  # ['benchmark.py', 'build', '--nobuild', '//:all']
  bazel_args = argv[1:]

  project_source = _resolve_path(FLAGS.project_source)
  need_project_clone = not os.path.isdir(project_source) or bool(FLAGS.project_commits)
  if not need_project_clone:
    _check_no_patch_in_place(project_source, [FLAGS.patch_file])

  # Building Bazel binaries
  bazel_binaries = [_resolve_path(b) for b in (FLAGS.bazel_binaries or [])]
  need_bazel_repo = bool(FLAGS.bazel_commits) or not bazel_binaries or bool(FLAGS.bisect)
  bazel_source = _resolve_path(FLAGS.bazel_source) if FLAGS.bazel_source else BAZEL_GITHUB_URL
  bazel_clone_repo = None
  bazel_commits = []

  if need_bazel_repo:
    logger.log('Preparing bazelbuild/bazel repository.')
    bazel_clone_repo = _setup_project_repo(
        BAZEL_CLONE_BASE_PATH + '/' + _get_clone_subdir(bazel_source),
        bazel_source)
    bazel_commits = _get_commits_topological(
        FLAGS.bazel_commits,
        bazel_clone_repo,
        'bazel_commits',
        fill_default=not FLAGS.bazel_commits and not bazel_binaries)

  # Set up project repo
  project_clone_repo = None

  if need_project_clone:
    logger.log('Preparing %s clone.' % project_source)
    project_clone_repo = _setup_project_repo(
        PROJECT_CLONE_BASE_PATH + '/' + _get_clone_subdir(project_source),
        project_source)
    project_commits = _get_commits_topological(FLAGS.project_commits,
                                               project_clone_repo,
                                               'project_commits')
  else:
    latest_commit_sha = _get_local_project_commit(project_source)
    logger.log('No project_commits specified, using the latest one: %s' % latest_commit_sha)
    project_commits = [latest_commit_sha]

  config = BenchmarkConfig.from_flags(
      bazel_commits=bazel_commits,
      bazel_binaries=bazel_binaries,
      project_commits=project_commits,
      bazel_source=bazel_source,
      project_source=project_source,
      env_configure=FLAGS.env_configure,
      runs=FLAGS.runs,
      warmup_runs=FLAGS.warmup_runs,
      max_outlier_reruns=FLAGS.max_outlier_reruns,
      interleave=FLAGS.interleave,
      collect_profile=FLAGS.collect_profile,
      collect_memory=FLAGS.collect_memory,
      collect_process_memory=FLAGS.collect_process_memory,
      collect_bep=FLAGS.collect_bep,
      patch_file=_resolve_path(FLAGS.patch_file),
      command=' '.join(bazel_args),
      clean=FLAGS.clean,
      shutdown=FLAGS.shutdown)

  return config, bazel_clone_repo, project_clone_repo


def main(argv):
  _flag_checks()

  config, bazel_clone_repo, project_clone_repo = _get_benchmark_config_and_clone_repos(
      argv)
  project_path = project_clone_repo.working_dir if project_clone_repo else _resolve_path(config.get_project_source())

  # A dictionary that maps a (bazel_commit, project_commit) tuple
  # to its benchmarking result.
  data = collections.OrderedDict()
  csv_data = collections.OrderedDict()
  if FLAGS.data_directory:
    data_directory = _resolve_path(FLAGS.data_directory)
    if not os.path.exists(data_directory):
      os.makedirs(data_directory)
  else:
    data_directory = tempfile.mkdtemp(prefix='benchmark.')
    logger.log('Using %s as data directory.' % data_directory)

  output_handling.create_latest_symlink(data_directory)

  # We use the start time as a unique identifier of this bazel-bench run.
  bazel_bench_uid = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')

  bazel_bin_base_path = _resolve_path(FLAGS.bazel_bin_dir) if FLAGS.bazel_bin_dir else BAZEL_BINARY_BASE_PATH

  if FLAGS.bisect:
    target_metric = FLAGS.bisect
    bazel_commits = config.get_bazel_commits()
    good_commit = bazel_commits[0]
    bad_commit = bazel_commits[1]
    unit = config.get_units()[0]
    project_commit = unit['project_commit']

    def eval_fn(commit):
      logger.log('--- Evaluating commit for bisection: %s ---' % commit)
      bazel_bin_path = _build_bazel_binary(
          commit, bazel_clone_repo, bazel_bin_base_path, FLAGS.platform)
      if project_clone_repo:
        project_clone_repo.git.checkout('-f', project_commit)
      if unit['env_configure'] is not None:
        _exec_command(
            unit['env_configure'], shell=True, cwd=project_path)

      results, _ = _run_benchmark(
          bazel_bin_path=bazel_bin_path,
          project_path=project_path,
          runs=unit['runs'],
          command=unit['command'],
          options=unit['options'],
          targets=unit['targets'],
          startup_options=unit['startup_options'],
          prefetch_ext_deps=FLAGS.prefetch_ext_deps,
          bazel_bench_uid=bazel_bench_uid,
          unit_num=0,
          collect_profile=False,
          data_directory=data_directory,
          bazel_identifier=commit,
          project_commit=project_commit,
          warmup_runs=unit.get('warmup_runs', FLAGS.warmup_runs),
          max_outlier_reruns=unit.get('max_outlier_reruns', FLAGS.max_outlier_reruns),
          collect_memory=unit.get('collect_memory', FLAGS.collect_memory),
          collect_process_memory=unit.get('collect_process_memory', FLAGS.collect_process_memory),
          collect_bep=unit.get('collect_bep', FLAGS.collect_bep),
          patch_file=unit.get('patch_file', FLAGS.patch_file))

      # Only successful runs count: a failing build is not a valid measurement
      # (and is usually misleadingly fast). If nothing remains, bisection.bisect
      # raises a BisectError.
      vals = Values()
      failed = 0
      for r in results:
        if r is None:
          continue
        if r.get('exit_status', 0) != 0:
          failed += 1
          continue
        if target_metric in r:
          vals.add(r[target_metric])
      if failed:
        logger.log_warn('%d/%d runs failed for commit %s and were excluded.' %
                        (failed, len(results), commit))
      return vals

    bisect_result = bisection.bisect(
        bazel_clone_repo,
        good_commit,
        bad_commit,
        eval_fn,
        target_metric=target_metric)

    summary_str = bisect_result.summary()
    print(summary_str)

    output_handling.export_file(
        data_directory, '{}_bisect.md'.format(bazel_bench_uid), '```\n' + summary_str + '\n```\n')

    logger.log('Done.')
    return

  # Build the bazel binaries, if necessary.
  for unit in config.get_units():
    if 'bazel_binary' in unit:
      unit['bazel_bin_path'] = unit['bazel_binary']
    elif 'bazel_commit' in unit:
      bazel_bin_path = _build_bazel_binary(unit['bazel_commit'],
                                           bazel_clone_repo,
                                           bazel_bin_base_path, FLAGS.platform)
      unit['bazel_bin_path'] = bazel_bin_path

  units = config.get_units()
  if FLAGS.interleave and len(units) > 1:
    unit_results = collections.defaultdict(list)
    unit_args = {}
    for i, unit in enumerate(units):
      bazel_identifier = unit['bazel_commit'] if 'bazel_commit' in unit else unit['bazel_binary']
      project_commit = unit['project_commit']
      os.chdir(project_path)
      if project_clone_repo:
        project_clone_repo.git.checkout('-f', project_commit)
      if unit['env_configure'] is not None:
        _exec_command(unit['env_configure'], shell=True, cwd=project_path)

      logger.log('=== PREPARING BAZEL [Unit #%d]: %s, PROJECT: %s ===' %
                 (i, bazel_identifier, project_commit))
      if FLAGS.prefetch_ext_deps:
        logger.log('Pre-fetching external dependencies...')
        _single_run(unit['bazel_bin_path'], unit['command'], unit['options'], unit['targets'], unit['startup_options'])

      warmup_runs = unit.get('warmup_runs', FLAGS.warmup_runs)
      if warmup_runs > 0:
        for w in range(1, warmup_runs + 1):
          logger.log('Starting warmup run %d/%d for Unit #%d:' % (w, warmup_runs, i))
          with patch_util.apply_patch(project_path, unit.get('patch_file', FLAGS.patch_file)):
            _single_run(unit['bazel_bin_path'], unit['command'], unit['options'], unit['targets'], unit['startup_options'])

      unit_args[i] = (unit['command'], unit['targets'], unit['options'])

    max_runs = max(u['runs'] for u in units)
    for run_idx in range(1, max_runs + 1):
      for i, unit in enumerate(units):
        if run_idx > unit['runs']:
          continue
        bazel_identifier = unit['bazel_commit'] if 'bazel_commit' in unit else unit['bazel_binary']
        project_commit = unit['project_commit']
        os.chdir(project_path)
        if project_clone_repo:
          project_clone_repo.git.checkout('-f', project_commit)
        if unit['env_configure'] is not None:
          _exec_command(unit['env_configure'], shell=True, cwd=project_path)

        logger.log('Starting benchmark run %d/%d for Unit #%d (%s):' %
                   (run_idx, unit['runs'], i, bazel_identifier))
        with patch_util.apply_patch(project_path, unit.get('patch_file', FLAGS.patch_file)):
          res = _run_single_benchmark_iteration(
              bazel_bin_path=unit['bazel_bin_path'],
              command=unit['command'],
              options=unit['options'],
              targets=unit['targets'],
              startup_options=unit['startup_options'],
              run_number=run_idx,
              total_runs=unit['runs'],
              unit_num=i,
              bazel_bench_uid=bazel_bench_uid,
              data_directory=data_directory,
              collect_profile=unit['collect_profile'],
              bazel_identifier=bazel_identifier,
              project_commit=project_commit,
              collect_memory=unit.get('collect_memory', FLAGS.collect_memory),
              collect_process_memory=unit.get('collect_process_memory', FLAGS.collect_process_memory),
              collect_bep=unit.get('collect_bep', FLAGS.collect_bep))
        unit_results[i].append(res)

    for i, unit in enumerate(units):
      bazel_identifier = unit['bazel_commit'] if 'bazel_commit' in unit else unit['bazel_binary']
      project_commit = unit['project_commit']
      results = unit_results[i]
      args = unit_args[i]
      max_outlier_reruns = unit.get('max_outlier_reruns', FLAGS.max_outlier_reruns)
      if max_outlier_reruns > 0:
        reruns_left = max_outlier_reruns
        reruns_performed = 0
        while reruns_left > 0:
          valid_indices = [
              idx for idx, r in enumerate(results)
              if r and 'wall' in r and r.get('exit_status', 0) == 0
          ]
          wall_vals = Values([results[idx]['wall'] for idx in valid_indices])
          outliers = wall_vals.get_outlier_indices()
          if not outliers:
            break
          med = wall_vals.median()
          worst_subidx = max(outliers, key=lambda idx: abs(wall_vals.values()[idx] - med))
          worst_idx = valid_indices[worst_subidx]
          logger.log(
              'Detected wall-time outlier (%.3fs) in Unit #%d. Performing outlier rerun (%d remaining)...'
              % (wall_vals.values()[worst_subidx], i, reruns_left))
          reruns_left -= 1
          reruns_performed += 1
          del results[worst_idx]
          os.chdir(project_path)
          if project_clone_repo:
            project_clone_repo.git.checkout('-f', project_commit)
          if unit['env_configure'] is not None:
            _exec_command(unit['env_configure'], shell=True, cwd=project_path)
          with patch_util.apply_patch(project_path, unit.get('patch_file', FLAGS.patch_file)):
            rerun_res = _run_single_benchmark_iteration(
                bazel_bin_path=unit['bazel_bin_path'],
                command=unit['command'],
                options=unit['options'],
                targets=unit['targets'],
                startup_options=unit['startup_options'],
                run_number=unit['runs'] + reruns_performed,
                total_runs=unit['runs'],
                unit_num=i,
                bazel_bench_uid=bazel_bench_uid,
                data_directory=data_directory,
                collect_profile=unit['collect_profile'],
                bazel_identifier=bazel_identifier,
                project_commit=project_commit,
                collect_memory=unit.get('collect_memory', FLAGS.collect_memory),
                collect_process_memory=unit.get('collect_process_memory', FLAGS.collect_process_memory),
                collect_bep=unit.get('collect_bep', FLAGS.collect_bep))
          results.append(rerun_res)

      collected = _collect_metrics(results)

      data[(i, bazel_identifier, project_commit)] = collected
      non_measurables = {
          'project_source': unit['project_source'],
          'platform': FLAGS.platform,
          'project_label': FLAGS.project_label
      }
      csv_data[(bazel_identifier, project_commit)] = {
          'results': results,
          'args': args,
          'non_measurables': non_measurables
      }
  else:
    for i, unit in enumerate(units):
      bazel_identifier = unit['bazel_commit'] if 'bazel_commit' in unit else unit['bazel_binary']
      project_commit = unit['project_commit']

      if project_clone_repo:
        project_clone_repo.git.checkout('-f', project_commit)
      if unit['env_configure'] is not None:
        _exec_command(
            unit['env_configure'], shell=True, cwd=project_path)

      results, args = _run_benchmark(
          bazel_bin_path=unit['bazel_bin_path'],
          project_path=project_path,
          runs=unit['runs'],
          command=unit['command'],
          options=unit['options'],
          targets=unit['targets'],
          startup_options=unit['startup_options'],
          prefetch_ext_deps=FLAGS.prefetch_ext_deps,
          bazel_bench_uid=bazel_bench_uid,
          unit_num=i,
          collect_profile=unit['collect_profile'],
          data_directory=data_directory,
          bazel_identifier=bazel_identifier,
          project_commit=project_commit,
          warmup_runs=unit.get('warmup_runs', FLAGS.warmup_runs),
          max_outlier_reruns=unit.get('max_outlier_reruns', FLAGS.max_outlier_reruns),
          collect_memory=unit.get('collect_memory', FLAGS.collect_memory),
          collect_process_memory=unit.get('collect_process_memory', FLAGS.collect_process_memory),
          collect_bep=unit.get('collect_bep', FLAGS.collect_bep),
          patch_file=unit.get('patch_file', FLAGS.patch_file))
      collected = _collect_metrics(results)

      data[(i, bazel_identifier, project_commit)] = collected
      non_measurables = {
          'project_source': unit['project_source'],
          'platform': FLAGS.platform,
          'project_label': FLAGS.project_label
      }
      csv_data[(bazel_identifier, project_commit)] = {
          'results': results,
          'args': args,
          'non_measurables': non_measurables
      }

  summary_text = create_summary(data, config.get_project_source())
  if sys.stdout.isatty():
    print(create_summary(data, config.get_project_source(), color=True))
  else:
    print(summary_text)

  csv_file_name = FLAGS.csv_file_name or '{}.csv'.format(bazel_bench_uid)
  txt_file_name = csv_file_name.replace('.csv', '.txt')

  output_handling.export_csv(data_directory, csv_file_name, csv_data)
  output_handling.export_file(data_directory, txt_file_name, summary_text)
  output_handling.export_markdown(data_directory, '{}.md'.format(bazel_bench_uid), data, config.get_project_source())
  output_handling.export_json(data_directory, '{}.json'.format(bazel_bench_uid), data, csv_data)

  # This is mostly for the nightly benchmark.
  if FLAGS.aggregate_json_profiles:
    aggr_json_profiles_csv_path = (
        '%s/%s' % (data_directory, DEFAULT_AGGR_JSON_PROFILE_FILENAME))
    handle_json_profiles_aggr(
        bazel_bench_uid=bazel_bench_uid,
        unit_num=i,
        bazel_commits=config.get_bazel_commits(),
        project_source=config.get_project_source(),
        project_commits=config.get_project_commits(),
        runs=FLAGS.runs,
        output_path=aggr_json_profiles_csv_path,
        data_directory=data_directory,
    )

  logger.log('Done.')


if __name__ == '__main__':
  app.run(main)
