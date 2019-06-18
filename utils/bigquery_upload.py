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
"""Handles the uploading of result CSV to BigQuery.
"""
import logger
import sys


def upload_to_bigquery(csv_file_path, project_id, dataset_id, table_id, location):
  """Uploads the csv file to BigQuery.

  Takes the configuration from GOOGLE_APPLICATION_CREDENTIALS.

  Args:
    csv_file_path: the path to the csv to be uploaded.
    project_id: the BigQuery project id.
    dataset_id: the BigQuery dataset id.
    table_id: the BigQuery table id.
    location: the BigQuery table's location.
  """
  # This is a workaround for https://github.com/bazelbuild/rules_python/issues/14
  from google.cloud import bigquery

  logger.log('Uploading the data to bigquery.')
  client = bigquery.Client(project=project_id)

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


