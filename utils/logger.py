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
import datetime
import sys

_COLOR_TMPL = {
    'info': '\033[34m%s\033[0m',     # Blue
    'warn': '\033[33m%s\033[0m',     # Yellow
    'error': '\033[31;1m%s\033[0m',   # Bold Red
}


def _format_message(text, color):
  timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
  msg = f'{timestamp}: {text}'
  if sys.stderr.isatty():
    return _COLOR_TMPL[color] % msg
  return msg


def log(text, *, warning=False, fatal=False):
  """Logs a message to stderr with timestamp."""
  if fatal:
    log_error(text)
    sys.exit(1)
  elif warning:
    log_warn(text)
  else:
    print(_format_message(text, 'info'), file=sys.stderr)
    sys.stderr.flush()


def log_warn(text):
  """Logs a warning message to stderr."""
  print(_format_message(text, 'warn'), file=sys.stderr)
  sys.stderr.flush()


def log_error(text):
  """Logs an error message to stderr."""
  print(_format_message(text, 'error'), file=sys.stderr)
  sys.stderr.flush()
