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
import csv
import json
import datetime
import socket
import getpass
import math

from utils.values import Values
import utils.logger as logger


def export_csv(data_directory, filename, data):
  """Exports the content of data to a csv file in data_directory

  Args:
    data_directory: the directory to store the csv file.
    filename: the name of the .csv file.
    data: the collected data to be exported.
    
  Returns:
    The path to the newly created csv file.
  """
  if not os.path.exists(data_directory):
    os.makedirs(data_directory)
  csv_file_path = os.path.join(data_directory, filename)
  logger.log('Writing raw data into csv file: %s' % str(csv_file_path))

  with open(csv_file_path, 'w') as csv_file:
    hostname = socket.gethostname()
    username = getpass.getuser()
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'project_source', 'project_commit', 'bazel_commit', 'run', 'cpu',
        'wall', 'system', 'memory', 'command', 'expressions', 'hostname',
        'username', 'options', 'exit_status', 'started_at', 'platform',
        'project_label'
    ])

    for (bazel_commit, project_commit), data_item in data.items():
      command, expressions, options = data_item['args']
      non_measurables = data_item['non_measurables']
      for idx, run in enumerate(data_item['results'], start=1):
        csv_writer.writerow([
            non_measurables['project_source'], project_commit, bazel_commit,
            idx, run['cpu'], run['wall'], run['system'], run.get('memory', ''), command,
            expressions, hostname, username, options, run['exit_status'],
            run['started_at'], non_measurables['platform'],
            non_measurables['project_label']
        ])
  return csv_file_path


def export_file(data_directory, filename, content):
  """Exports the content of data to a file in data_directory

  Args:
    data_directory: the directory to store the file.
    filename: the name of the file.
    content: the content to be exported.

  Returns:
    The path to the newly created file.
  """
  if not os.path.exists(data_directory):
    os.makedirs(data_directory)
  out_file_path = os.path.join(data_directory, filename)

  with open(out_file_path, 'w') as out_file:
    out_file.write(content)

  return out_file_path


def export_markdown(data_directory, filename, data, project_source):
  """Exports benchmarking results to a GitHub Flavored Markdown table.

  Args:
    data_directory: The directory to store the markdown file.
    filename: The name of the .md file.
    data: OrderedDict mapping (unit_num, bazel_identifier, project_commit) -> metric -> Values.
    project_source: URL or path of the benchmarked project.

  Returns:
    The path to the newly created markdown file.
  """
  if not os.path.exists(data_directory):
    os.makedirs(data_directory)
  md_file_path = os.path.join(data_directory, filename)
  logger.log('Writing Markdown report into: %s' % str(md_file_path))

  unit_symbols = {
      'wall': 's',
      'cpu': 's',
      'system': 's',
      'memory': 'MB',
      'peakProcessRss': 'MB',
      'peakPostGcHeapSize': 'MB',
      'usedHeapSizePostBuild': 'MB',
      'edenSpaceGarbage': 'MB',
      'oldGenGarbage': 'MB',
      'analysisPhaseTime': 's',
      'executionPhaseTime': 's',
  }

  lines = []
  lines.append('# Bazel Benchmark Report')
  lines.append('')
  if project_source:
    lines.append('**Project:** `%s`' % project_source)
    lines.append('')

  lines.append('| Unit | Bazel Version | Project Commit | Metric | Mean ± Stddev | Median | Speedup (vs Baseline) | Significance |')
  lines.append('| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |')

  items = list(data.items())
  if not items:
    with open(md_file_path, 'w') as md_file:
      md_file.write('\n'.join(lines))
    return md_file_path

  (base_idx, base_bazel, base_project), base_collected = items[0]
  base_non_zero = {
      i: ec for i, ec in enumerate(base_collected.get('exit_status', Values()).items())
      if ec != 0
  }

  for (u_idx, bazel_identifier, project_commit), collected in items:
    non_zero_runs = {
        i: ec for i, ec in enumerate(collected.get('exit_status', Values()).items())
        if ec != 0
    }
    unit_label = 'Unit #%d%s' % (u_idx, ' (Baseline)' if u_idx == 0 else '')

    first_metric = True
    for metric, values in collected.items():
      if metric in ['exit_status', 'started_at', 'invocation_id']:
        continue
      clean_vals = values.exclude_from_indexes(non_zero_runs.keys())
      if not clean_vals.values_wo_nan():
        continue

      m_unit = unit_symbols.get(metric, '')
      mean_val = clean_vals.mean()
      stddev_val = clean_vals.stddev()
      median_val = clean_vals.median()

      if not math.isnan(stddev_val):
        mean_str = '%.3f%s ± %.3f%s' % (mean_val, m_unit, stddev_val, m_unit)
      else:
        mean_str = '%.3f%s' % (mean_val, m_unit)
      median_str = '%.3f%s' % (median_val, m_unit)

      if u_idx == 0:
        speedup_str = '1.00x (baseline)'
        sig_str = '-'
      else:
        if metric in base_collected:
          base_clean_vals = base_collected[metric].exclude_from_indexes(base_non_zero.keys())
          if clean_vals.is_unchanged(base_clean_vals):
            speedup_str = '-'
            sig_str = '-'
          else:
            ratio, r_err, pct_diff = clean_vals.speedup_ratio(base_clean_vals)
            sig = clean_vals.significance_label(base_clean_vals.values())
            if not math.isnan(ratio):
              if r_err > 0.0:
                speedup_str = '%.2f ± %.2fx (%+.1f%%)' % (ratio, r_err, pct_diff)
              else:
                speedup_str = '%.2f%s (%+.1f%%)' % (ratio, 'x', pct_diff)
              sig_str = sig
            else:
              speedup_str = 'N/A'
              sig_str = '-'
        else:
          speedup_str = '-'
          sig_str = '-'

      unit_col = unit_label if first_metric else ''
      bazel_col = '`%s`' % bazel_identifier if first_metric else ''
      project_col = '`%s`' % project_commit if first_metric else ''
      first_metric = False

      lines.append('| %s | %s | %s | %s | %s | %s | %s | %s |' %
                   (unit_col, bazel_col, project_col, metric, mean_str,
                    median_str, speedup_str, sig_str))

  lines.append('')
  content = '\n'.join(lines)
  with open(md_file_path, 'w') as md_file:
    md_file.write(content)
  return md_file_path


def export_json(data_directory, filename, data, csv_data=None, metadata=None):
  """Exports benchmarking results to a structured JSON file.

  Args:
    data_directory: The directory to store the json file.
    filename: The name of the .json file.
    data: OrderedDict mapping (unit_num, bazel_identifier, project_commit) -> metric -> Values.
    csv_data: Optional dict mapping (bazel_identifier, project_commit) -> {'results': [...], 'args': ..., ...}.
    metadata: Optional metadata dict.

  Returns:
    The path to the newly created JSON file.
  """
  if not os.path.exists(data_directory):
    os.makedirs(data_directory)
  json_file_path = os.path.join(data_directory, filename)
  logger.log('Writing structured JSON report into: %s' % str(json_file_path))

  meta = {
      'hostname': socket.gethostname(),
      'username': getpass.getuser(),
      'generated_at': datetime.datetime.utcnow().isoformat(),
  }
  if metadata:
    meta.update(metadata)

  items = list(data.items())
  base_collected = items[0][1] if items else None
  base_non_zero = {}
  if base_collected:
    base_non_zero = {
        i: ec for i, ec in enumerate(base_collected.get('exit_status', Values()).items())
        if ec != 0
    }

  units_list = []
  for (u_idx, bazel_identifier, project_commit), collected in items:
    non_zero_runs = {
        i: ec for i, ec in enumerate(collected.get('exit_status', Values()).items())
        if ec != 0
    }

    metrics_dict = {}
    comparison_dict = {}

    for metric, values in collected.items():
      if metric in ['exit_status', 'started_at', 'invocation_id']:
        continue
      clean_vals = values.exclude_from_indexes(non_zero_runs.keys())
      if not clean_vals.values_wo_nan():
        continue

      ci_low, ci_high = clean_vals.confidence(0.95)
      inliers, outliers = clean_vals.get_inliers_and_outliers()

      metrics_dict[metric] = {
          'mean': None if math.isnan(clean_vals.mean()) else clean_vals.mean(),
          'median': None if math.isnan(clean_vals.median()) else clean_vals.median(),
          'min': None if math.isnan(clean_vals.min()) else clean_vals.min(),
          'max': None if math.isnan(clean_vals.max()) else clean_vals.max(),
          'stddev': None if math.isnan(clean_vals.stddev()) else clean_vals.stddev(),
          'ci_95': [
              None if math.isnan(ci_low) else ci_low,
              None if math.isnan(ci_high) else ci_high,
          ],
          'inliers_count': len(inliers.values()),
          'outliers_count': len(outliers.values()),
          'raw_values': [v if math.isfinite(v) else None for v in clean_vals.values()],
      }

      if u_idx > 0 and base_collected and metric in base_collected:
        base_clean = base_collected[metric].exclude_from_indexes(base_non_zero.keys())
        if clean_vals.is_unchanged(base_clean):
          comparison_dict[metric] = {
              'speedup_ratio': 1.0,
              'speedup_ratio_error': 0.0,
              'percent_diff': 0.0,
              'significance': 'unchanged',
              'pval': 0.0,
          }
        else:
          ratio, r_err, pct_diff = clean_vals.speedup_ratio(base_clean)
          sig = clean_vals.significance_label(base_clean.values())
          pval = clean_vals.pval(base_clean.values())
          comparison_dict[metric] = {
              'speedup_ratio': None if math.isnan(ratio) else ratio,
              'speedup_ratio_error': None if math.isnan(r_err) else r_err,
              'percent_diff': None if math.isnan(pct_diff) else pct_diff,
              'significance': sig,
              'pval': None if math.isnan(pval) else pval,
          }
      elif u_idx == 0:
        comparison_dict[metric] = {
            'speedup_ratio': 1.0,
            'speedup_ratio_error': 0.0,
            'percent_diff': 0.0,
            'significance': 'baseline',
            'pval': 0.0,
        }

    raw_runs = []
    args = None
    if csv_data and (bazel_identifier, project_commit) in csv_data:
      c_item = csv_data[(bazel_identifier, project_commit)]
      raw_runs = c_item.get('results', [])
      args = c_item.get('args', None)

    units_list.append({
        'unit_num': u_idx,
        'bazel_identifier': bazel_identifier,
        'project_commit': project_commit,
        'args': args,
        'metrics': metrics_dict,
        'comparison_against_baseline': comparison_dict,
        'raw_runs': raw_runs,
    })

  output_obj = {
      'metadata': meta,
      'units': units_list,
  }

  with open(json_file_path, 'w') as jf:
    json.dump(output_obj, jf, indent=2, default=str)

  return json_file_path


_LATEST_SYMLINK_PATH = '/tmp/benchmark.latest'


def create_latest_symlink(data_directory, symlink_path=_LATEST_SYMLINK_PATH):
  """Creates a symlink /tmp/benchmark.latest pointing to the data directory."""
  try:
    if os.path.islink(symlink_path):
      os.unlink(symlink_path)
    elif os.path.exists(symlink_path):
      logger.log_warn(
          'Cannot create symlink %s: A regular file with that name exists.'
          % symlink_path)
      return
    os.symlink(data_directory, symlink_path)
    logger.log('Created symlink %s -> %s' % (symlink_path, data_directory))
  except Exception as e:
    logger.log_warn(
        'Failed to create symlink %s -> %s: %s' % (symlink_path, data_directory, e))

