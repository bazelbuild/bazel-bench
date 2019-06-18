"""A library that holds the bulk of the logic for merging JSON profiles.

Collect median duration of events across these profiles.
"""
from __future__ import division

import csv
import gzip
import json
import os


def _median(lst):
  """Returns the median of the input list.

  Args:
    lst: the input list.

  Returns:
    The median of the list, or None if the list is empty/None.
  """
  sorted_lst = sorted(lst)
  length = len(sorted_lst)
  if length % 2:
    return sorted_lst[length // 2]
  return (sorted_lst[length // 2 - 1] + sorted_lst[length // 2]) / 2


def write_to_csv(
    bazel_source, project_source, project_commit, event_list, output_csv_path):
  """Writes the event_list to output_csv_path.

  event_list format:
  [{'cat': <string>, 'name': <string>, 'dur': <int>}, ...]

  Args:
    bazel_source: the bazel commit or path to the bazel binary from which these
      JSON profiles were collected.
    project_source: the project on which the runs that generated these JSON
      projects were performed.
    project_commit: the project commit on which the Bazel runs were performed.
    event_list: the list of events, aggregated from the JSON profiles.
    output_csv_path: a path to the output CSV file.
  """
  output_dir = os.path.dirname(output_csv_path)
  if not os.path.exists(output_dir):
    os.makedirs(output_dir)

  with open(output_csv_path, 'w') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(
        ['bazel_source', 'project_source', 'project_commit',
         'cat', 'name', 'dur'])

    for event in event_list:
      csv_writer.writerow(
          [bazel_source, project_source, project_commit,
           event['cat'], event['name'], event['dur']])


def _accumulate_event_duration(event_list, accum_dict, only_phases=False):
  """Fill up accum_dict by accummulating durations of each event.

  Also create the entries for each phase by subtracting the build phase markers'
  ts attribute.

  Args:
    event_list: the list of event objects.
    accum_dict: the dict to be filled up with a mapping of the following format:
      { <name>: { name: ..., cat: ..., dur_list: [...]}, ...}
    only_phases: only collect entries from phase markers.
  """
  # A list of tuples of the form (marker, occurrence time in micro s)
  build_markers_ts_pairs = []
  max_ts = 0

  # Only collect events with a duration.
  # Special case: markers that indicates beginning/end of execution.
  for event in event_list:
    if 'ts' in event:
      max_ts = max(max_ts, event['ts'])

    if 'cat' in event and event['cat'] == 'build phase marker':
      build_markers_ts_pairs.append((event['name'], event['ts']))

    if 'dur' not in event:
      continue

    if not only_phases:
      if event['name'] not in accum_dict:
        accum_dict[event['name']] = {
            'name': event['name'],
            'cat': event['cat'],
            'dur_list': []
        }
      accum_dict[event['name']]['dur_list'].append(event['dur'])

  # Append an artificial marker that signifies the end of the run.
  # This is to determine the duration from the last marker to the actual end of
  # the run and will not end up in the final data.
  build_markers_ts_pairs.append((None, max_ts))

  # Fill in the markers.
  for i, marker_ts_pair in enumerate(build_markers_ts_pairs[:-1]):
    marker, ts = marker_ts_pair
    _, next_ts = build_markers_ts_pairs[i + 1]

    if marker not in accum_dict:
      accum_dict[marker] = {
          'name': marker,
          'cat': 'build phase marker',
          'dur_list': []
      }
    current_phase_duration_millis = (next_ts - ts) / 1000
    accum_dict[marker]['dur_list'].append(current_phase_duration_millis)


def _aggregate_from_accum_dict(accum_dict):
  """Aggregate the result from the accummulated dict.

  Calculate the median of the durations for each event.

  Args:
    accum_dict: the dict to be filled up with a mapping of the following format:
      { <name>: { name: ..., cat: ..., dur_list: [...]}, ...}

  Returns:
    A list of the following format:
      [{ name: ..., cat: ..., dur: ... }]
  """
  result = []
  for obj in accum_dict.values():
    result.append({
        'name': obj['name'],
        'cat': obj['cat'],
        'dur': _median(obj['dur_list'])
    })
  return result


def aggregate_data(input_profiles, only_phases=False):
  """Produces the aggregated data from the JSON profile inputs.

  Collects information on cat, name and median duration of the events in the
  JSON profiles.

  Args:
    input_profiles: a list of paths to .profile or .profile.gz files.
    only_phases: only output entries from phase markers.

  Returns:
    The list of objects which contain the info about cat, name and median
    duration of events.
  """
  # A map from event name to an object which accumulates the durations.
  accum_dict = dict()
  for file_path in input_profiles:
    if file_path.endswith('.gz'):
      with gzip.GzipFile(file_path, 'r') as gz_input_file:
        event_list = json.loads(gz_input_file.read().decode('utf-8'))
    else:
      with open(file_path, 'r') as input_file:
        event_list = json.load(input_file)

    # The events in the JSON profiles can be presented directly as a list,
    # or as the value of key 'traceEvents'.
    if 'traceEvents' in event_list:
      event_list = event_list['traceEvents']
    _accumulate_event_duration(event_list, accum_dict, only_phases)

  return _aggregate_from_accum_dict(accum_dict)

