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
"""Module to handle Bazel arguments parsing.

2 strategies to parse arguments: via Build Event json or manually via the
argument string.

The returned arguments are in canonical form. This is guaranteed for
parse_bazel_args_from_build_event and a soft requirement for
parse_bazel_args_from_canonical_str.
"""

import json
import logger

def _to_str_list(unicode_str_list):
  """Converts a unicode string list to a string list."""
  return list(map(str, unicode_str_list))


def _get_section_content(events, section_label):
  """Extracts a section content from events, given a section_label.

  Args:
    events: the events json parsed from file.
    section_label: the label of the section. e.g. 'residual' or 'command'.

  Returns:
    A list containing the content of the section.
  """
  # It's guaranteed that there's only 1 structuredCommandLine event with
  # commandLineLabel == 'canonical'
  structuredCommandLine = list(
      filter(
          lambda x: 'structuredCommandLine' in x
              and 'commandLineLabel' in x['structuredCommandLine']
              and x['structuredCommandLine']['commandLineLabel'] == 'canonical',
          events))[0]

  sections = list(
      filter(
          lambda x: 'sectionLabel' in x
              and x['sectionLabel'] == section_label,
          structuredCommandLine['structuredCommandLine']['sections'])
          )

  if not sections:
    return []

  # It's guaranteed that each structuredCommandLine only has 1 section with
  # a particular 'sectionLabel' value.
  return sections[0]['chunkList']['chunk']


def _extract_residual_expressions(events):
  residual_expressions = _get_section_content(events, 'residual')
  return _to_str_list(residual_expressions)


def _extract_command(events):
  # It's guaranteed that the command section only has 1 element.
  command = _get_section_content(events, 'command')[0]
  return command


def _extract_options(events):
  optionsParsed = list(filter(lambda x: 'optionsParsed' in x, events))

  # It's guaranteed that there's only 1 'optionsParsed' event.
  options = optionsParsed[0]['optionsParsed']['explicitCmdLine']
  # Exclude the --build_event_json_file option added by the script.
  # The --build_event_json_file option added by the script is guaranteed
  # to come last.
  return _to_str_list(options[:-1])


def parse_bazel_args_from_build_event(build_event_json_path):
  """Parse the bazel arguments from the build_env json file.

  Args:
    build_event_json_path: The absolute path to the build event json file.
  """
  events = []
  with open(build_event_json_path, 'r') as f:
    for line in f:
      events.append(json.loads(line))
  return _extract_command(events), _extract_residual_expressions(events), _extract_options(events)


def parse_bazel_args_from_canonical_str(args):
  """Parse the bazel arguments from the input string in canonical form.

  <command> [<canonical options>] [<expressions>]

  Parsing startup options is not supported. We only allow bazelrc through a
  separate flag.

  Args:
    args: the concatenated string of arguments to be passed to bazel binary.
      Has to be in canonical form.
  """
  logger.log_warn('Warning: Disabling prefetch_ext_deps requires the command to be in ' \
      'canonical form: <command> [<canonical options>] [<expressions>]. ' \
      'E.g. build --compilation_mode=opt -- //:all')

  # The command is always the first element.
  command = args[0]
  options = []
  expressions = []

  for i in range(1, len(args)):
    if not args[i].startswith('--'):
      expressions = args[i:]
      break
    options.append(args[i])

  return command, expressions, options
