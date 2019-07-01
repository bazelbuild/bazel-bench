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
"""Utility module to handle logging for the benchmarking script."""
import sys
from absl import logging

_COLOR_TMPL = {
    'info': '\033[32m%s\033[0m',  # Green
    'warn': '\033[33m%s\033[0m',  # Yellow
    'error': '\033[31m%s\033[0m',  # Red
}


def _maybe_colorize_text(text, color):
  """Colorize the text if running on a terminal."""
  if not sys.stdout.isatty():
    return text
  return _COLOR_TMPL[color] % text


def log(text):
  """Logs a message using the logger singleton."""
  logging.info(_maybe_colorize_text(text, 'info'))


def log_warn(text):
  """Logs a warning message using the logger singleton."""
  logging.warn(_maybe_colorize_text(text, 'warn'))

def log_error(text):
  """Logs an error message using the logger singleton."""
  logging.error(_maybe_colorize_text(text, 'error'))

