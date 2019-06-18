r"""A simple script to aggregate JSON profiles.

Collect median duration of events across these profiles.

Usage:
  bazel run json_profiles_merger -- \
  --bazel_source=/usr/bin/bazel \
  --project_source=https://github.com/bazelbuild/bazel \
  --project_commit=2 \
  --output_path=/tmp/median_dur.csv \
  --upload_data_to=project-id:dataset-id:table-id:location \
  -- \
  *.profile
"""
from absl import app
from absl import flags

import json_profiles_merger_lib as lib
import output_handling

FLAGS = flags.FLAGS
flags.DEFINE_string('output_path', None, 'The path to the output file.')
flags.DEFINE_string(
    'bazel_source', None,
    ('(Optional) The bazel commit or path to the bazel binary from which these'
     'JSON profiles were collected.'))
flags.DEFINE_string(
    'project_source', None,
    ('(Optional) The project on which the runs that generated these JSON'
     'profiles were performed.'))
flags.DEFINE_string(
    'project_commit', None,
    '(Optional) The project commit on which the Bazel runs were performed.')
flags.DEFINE_string(
    'upload_data_to', None,
    'Uploads data to bigquery, requires output_path to be set. '
    'The details of the BigQuery table to upload results to specified in '
    'the form: <project_id>:<dataset_id>:<table_id>:<location>.')
flags.DEFINE_boolean(
    'only_phases', False,
    'Whether to only include events from phase markers in the final output.')

def main(argv):
  # Discard the first argument (the binary).
  input_profiles = argv[1:]
  lib.aggregate_data(
      FLAGS.bazel_source,
      FLAGS.project_source,
      FLAGS.project_commit,
      input_profiles,
      FLAGS.output_path,
      FLAGS.only_phases)
  if FLAGS.upload_data_to:
    project_id, dataset_id, table_id, location = FLAGS.upload_data_to.split(':')
    output_handling.upload_csv(
        csv_file_path=FLAGS.output_path,
        project_id=project_id,
        dataset_id=dataset_id,
        table_id=table_id,
        location=location)


if __name__ == '__main__':
  app.run(main)
