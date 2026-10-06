import collections
import datetime
import json
import os
import shutil
import tempfile
import unittest

from utils import output_handling
from utils.values import Values


class OutputHandlingTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def test_export_markdown(self):
    data = collections.OrderedDict()

    unit0 = {
        'wall': Values([10.0, 10.2, 9.8]),
        'cpu': Values([20.0, 20.1, 19.9]),
        'exit_status': Values([0, 0, 0]),
    }
    unit1 = {
        'wall': Values([5.0, 5.1, 4.9]),
        'cpu': Values([10.0, 10.1, 9.9]),
        'exit_status': Values([0, 0, 0]),
    }
    data[(0, 'bazel_1', 'commit_a')] = unit0
    data[(1, 'bazel_2', 'commit_a')] = unit1

    md_path = output_handling.export_markdown(
        self.temp_dir, 'report.md', data, 'https://github.com/example/repo')

    self.assertTrue(os.path.exists(md_path))
    with open(md_path, 'r') as f:
      content = f.read()

    self.assertIn('# Bazel Benchmark Report', content)
    self.assertIn('https://github.com/example/repo', content)
    self.assertIn('Unit #0 (Baseline)', content)
    self.assertIn('Unit #1', content)
    self.assertIn('1.00x (baseline)', content)
    self.assertIn('2.00', content)

  def test_export_json(self):
    data = collections.OrderedDict()
    unit0 = {
        'wall': Values([10.0, 10.0]),
        'exit_status': Values([0, 0]),
    }
    unit1 = {
        'wall': Values([5.0, 5.0]),
        'exit_status': Values([0, 0]),
    }
    data[(0, 'bazel_1', 'commit_a')] = unit0
    data[(1, 'bazel_2', 'commit_a')] = unit1

    now = datetime.datetime.now()
    csv_data = {
        ('bazel_1', 'commit_a'): {
            'results': [{'wall': 10.0, 'exit_status': 0, 'started_at': now}],
            'args': ('build', ['//:all'], ['--nobuild']),
        },
        ('bazel_2', 'commit_a'): {
            'results': [{'wall': 5.0, 'exit_status': 0, 'started_at': now}],
            'args': ('build', ['//:all'], ['--nobuild']),
        },
    }

    json_path = output_handling.export_json(
        self.temp_dir, 'report.json', data, csv_data=csv_data)

    self.assertTrue(os.path.exists(json_path))
    with open(json_path, 'r') as f:
      parsed = json.load(f)

    self.assertIn('metadata', parsed)
    self.assertIn('units', parsed)
    self.assertEqual(2, len(parsed['units']))
    self.assertEqual('bazel_1', parsed['units'][0]['bazel_identifier'])
    self.assertEqual('bazel_2', parsed['units'][1]['bazel_identifier'])
    self.assertEqual(2.0, parsed['units'][1]['comparison_against_baseline']['wall']['speedup_ratio'])
    self.assertEqual(str(now), parsed['units'][0]['raw_runs'][0]['started_at'])

  def test_create_latest_symlink(self):
    target_dir = os.path.join(self.temp_dir, 'run_1')
    os.makedirs(target_dir)
    symlink_path = os.path.join(self.temp_dir, 'latest')

    output_handling.create_latest_symlink(target_dir, symlink_path=symlink_path)
    self.assertTrue(os.path.islink(symlink_path))
    self.assertEqual(os.path.realpath(symlink_path), os.path.realpath(target_dir))

    # Update to another run
    target_dir_2 = os.path.join(self.temp_dir, 'run_2')
    os.makedirs(target_dir_2)
    output_handling.create_latest_symlink(target_dir_2, symlink_path=symlink_path)
    self.assertTrue(os.path.islink(symlink_path))
    self.assertEqual(os.path.realpath(symlink_path), os.path.realpath(target_dir_2))

  def test_create_latest_symlink_regular_file_exists(self):
    target_dir = os.path.join(self.temp_dir, 'run_1')
    os.makedirs(target_dir)
    regular_file = os.path.join(self.temp_dir, 'latest')
    with open(regular_file, 'w') as f:
      f.write('regular')

    output_handling.create_latest_symlink(target_dir, symlink_path=regular_file)
    self.assertFalse(os.path.islink(regular_file))
    with open(regular_file, 'r') as f:
      self.assertEqual('regular', f.read())


if __name__ == '__main__':
  unittest.main()

