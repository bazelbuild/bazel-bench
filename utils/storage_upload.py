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
"""Handles the uploading of results to Storage.
"""
import logger

from google.cloud import storage


def upload_to_storage(file_path, project_id, bucket_id, destination):
  """Uploads the file to Storage.

  Takes the configuration from GOOGLE_APPLICATION_CREDENTIALS.

  Args:
    file_path: the path to the file to be uploaded.
    project_id: the GCP project id.
    bucket_id: the Storage bucket.
    destination: the path to the destination on the bucket.
  """
  logger.log('Uploading data to Storage.')
  client = storage.Client(project=project_id)
  bucket = client.get_bucket(bucket_id)
  blob = bucket.blob(destination)

  blob.upload_from_filename(file_path)

  logger.log(
      'Uploaded {} to {}/{}.'.format(file_path, bucket_id, destination))

