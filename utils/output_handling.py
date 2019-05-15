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

import sys
import os
import csv
import socket
import getpass
import uuid

import logger


def export_csv(data_directory, data, project_source):
  """Exports the content of data to a csv file in data_directory

  Args:
    data_directory: the directory to store the csv file.
    data: the collected data to be exported.
    project_source: either a path to the local git project to be built or a
      https url to a GitHub repository.

  Returns:
    The path to the newly created csv file.
  """
  if not os.path.exists(data_directory):
    os.makedirs(data_directory)
  csv_file_path = data_directory + str(uuid.uuid4()) + '.csv'
  logger.log('Writing raw data into csv file: %s' % str(csv_file_path))

  with open(csv_file_path, 'w') as csv_file:
    hostname = socket.gethostname()
    username = getpass.getuser()
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'project_source', 'project_commit', 'bazel_commit', 'run', 'cpu',
        'wall', 'system', 'memory', 'command', 'expressions', 'hostname',
        'username', 'options', 'exit_status', 'started_at'
    ])

    for (bazel_commit, project_commit), results_and_args in data.items():
      command, expressions, options = results_and_args['args']
      for idx, run in enumerate(results_and_args['results'], start=1):
        csv_writer.writerow([
            project_source, project_commit, bazel_commit, idx, run['cpu'],
            run['wall'], run['system'], run['memory'], command, expressions,
            hostname, username, options, run['exit_status'], run['started_at']
        ])
  return csv_file_path


def upload_csv(csv_file_path, bigquery_cfg):
  """Uploads the csv file to BigQuery.

  Takes the configuration from config.json.

  Args:
    csv_file_path: the path to the csv to be uploaded.
    bigquery_cfg: The string representing the BigQuery table config. Comes in
      the form <dataset_id>:<table_id>:<location>
  """
  # This is a workaround for
  # https://github.com/bazelbuild/rules_python/issues/14
  from google.cloud import bigquery

  logger.log('Uploading the data to bigquery.')
  client = bigquery.Client()
  dataset_id, table_id, location = bigquery_cfg.split(':')

  dataset_ref = client.dataset(dataset_id)
  table_ref = dataset_ref.table(table_id)

  job_config = bigquery.LoadJobConfig()
  job_config.source_format = bigquery.SourceFormat.CSV
  job_config.skip_leading_rows = 1
  job_config.autodetect = False

  # load table to get schema
  table = client.get_table(table_ref)
  job_config.schema = table.schema

  with open(str(csv_file_path), 'rb') as source_file:
    job = client.load_table_from_file(
        source_file, table_ref, location=location, job_config=job_config)

  try:
    job.result()  # Waits for table load to complete.
  except Exception:
    print('Uploading failed with: %s' % str(job.errors))
    sys.exit(-1)
  logger.log('Uploaded {} rows into {}:{}.'.format(job.output_rows, dataset_id,
                                                   table_id))
