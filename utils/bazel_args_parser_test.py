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
"""Tests for utils.bazel_args_parser."""
import tempfile
import mock
import unittest
import json
import bazel_args_parser as parser

# A portion of a typical build event json output.
fake_events = [
  {
    "structuredCommandLine": {
      "commandLineLabel": "canonical",
      "sections": [
        {
          "sectionLabel": "should_not_include",
          "chunkList": {
            "chunk": [
              "should_not_include"
            ]
          }
        },
        {
          "sectionLabel": "command",
          "chunkList": {
            "chunk": [
              "aquery"
            ]
          }
        },
        {
          "sectionLabel": "residual",
          "chunkList": {
            "chunk": [
              "deps(//src:bazel)"
            ]
          }
        }
      ]
    },
    "id": {
      "structuredCommandLine": {
        "commandLineLabel": "canonical"
      }
    }
  },
  {
    "structuredCommandLine": {
      "commandLineLabel": "should_not_include",
      "sections": []
    },
    "id": {
      "structuredCommandLine": {
        "commandLineLabel": "should_not_include"
      }
    }
  },
  {
    "optionsParsed": {
      "explicitCmdLine": [
        "--option1",
        "--option2=xyz",
        "--build_event_json_file=abc" # Refer to bazel_args_parser._extract_options
      ]
    },
    "id": {
      "optionsParsed": {}
    }
  }
]

class BazelArgsParserTest(unittest.TestCase):

  def test_get_section_content(self):
    command_content = parser._get_section_content(fake_events, 'command')
    residual_content = parser._get_section_content(fake_events, 'residual')
    empty_content = parser._get_section_content(fake_events, 'invalid_key')

    self.assertEqual(command_content, ['aquery'])
    self.assertEqual(residual_content, ['deps(//src:bazel)'])
    self.assertEqual(empty_content, [])

  def test_extract_residual_expressions(self):
    residual = parser._extract_residual_expressions(fake_events)
    self.assertEqual(residual, ['deps(//src:bazel)'])

  def test_extract_command(self):
    command = parser._extract_command(fake_events)
    self.assertEqual(command, 'aquery')

  def test_extract_options(self):
    options = parser._extract_options(fake_events)
    self.assertEqual(options, ['--option1', '--option2=xyz'])

  def test_parse_bazel_args_from_build_event(self):
    fake_file_content = '\n'.join([json.dumps(event) for event in fake_events])
    with tempfile.NamedTemporaryFile() as bep_json:
      bep_json.write(fake_file_content)
      bep_json.flush()
      command, expressions, options = parser.parse_bazel_args_from_build_event(bep_json.name)

    self.assertEqual(command, 'aquery')
    self.assertEqual(options, ['--option1', '--option2=xyz'])
    self.assertEqual(expressions, ['deps(//src:bazel)'])

  @mock.patch.object(parser.logger, 'log_warn')
  def test_parse_bazel_args_from_canonical_str(self, _):
    args = ['aquery', '--option1', '--option2=xyz', 'deps(//src:bazel)']
    command, expressions, options = parser.parse_bazel_args_from_canonical_str(args)

    self.assertEqual(command, 'aquery')
    self.assertEqual(options, ['--option1', '--option2=xyz'])
    self.assertEqual(expressions, ['deps(//src:bazel)'])

if __name__ == '__main__':
  unittest.main()
