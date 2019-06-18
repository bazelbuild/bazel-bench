"""Tests for json_profiles_merger_lib."""

import json_profiles_merger_lib as lib
import unittest

class JsonProfilesMergerLibTest(unittest.TestCase):

  def test_accumulate_event_duration(self):
    event_list_1 = [
        {
            'name': 'to_skip_no_dur',
        },
        {
            'cat': 'fake_cat',
            'name': 'fake_name',
            'dur': 3,
            'non_dur': 'something'
        },
    ]

    event_list_2 = [
        {
            'name': 'to_skip_no_dur',
        },
        {
            'cat': 'fake_cat',
            'name': 'fake_name',
            'dur': 1,
            'non_dur': 'something'
        },
    ]

    accum_dict = {}
    lib._accumulate_event_duration(event_list_1, accum_dict)
    self.assertEqual(
        {
            'fake_name': {
                'cat': 'fake_cat',
                'name': 'fake_name',
                'dur_list': [3]
            },
        }, accum_dict)
    lib._accumulate_event_duration(event_list_2, accum_dict)
    self.assertEqual(
        {
            'fake_name': {
                'cat': 'fake_cat',
                'name': 'fake_name',
                'dur_list': [3, 1]
            }
        }, accum_dict)

  def test_accumulate_build_phase_marker(self):
    event_list_3 = [
        {
            'name': 'to_skip_no_dur',
        },
        {
            'cat': 'build phase marker',
            'name': 'phase1',
            'ts': 1000
        },
        {
            'cat': 'build phase marker',
            'name': 'phase2',
            'ts': 10000
        },
        {
            'cat': 'fake_cat',
            'name': 'fake_name',
            'dur': 1,
            'ts': 10001,
            'non_dur': 'something'
        },
    ]

    accum_dict = {}
    lib._accumulate_event_duration(event_list_3, accum_dict)
    self.assertEqual(
        {
            'phase1': {
                'cat': 'build phase marker',
                'name': 'phase1',
                'dur_list': [9.0]
            },
            'phase2': {
                'cat': 'build phase marker',
                'name': 'phase2',
                'dur_list': [0.001]
            },
            'fake_name': {
                'cat': 'fake_cat',
                'name': 'fake_name',
                'dur_list': [1]
            },
        }, accum_dict)


  def test_accumulate_only_phase_marker(self):
    event_list = [
        {
            'name': 'to_skip_no_dur',
        },
        {
            'cat': 'build phase marker',
            'name': 'phase1',
            'ts': 1000
        },
        {
            'cat': 'build phase marker',
            'name': 'phase2',
            'ts': 10000
        },
        {
            'cat': 'fake_cat',
            'name': 'fake_name',
            'dur': 1,
            'ts': 10001,
            'non_dur': 'something'
        },
    ]

    accum_dict = {}
    lib._accumulate_event_duration(event_list, accum_dict, only_phases=True)
    self.assertEqual(
        {
            'phase1': {
                'cat': 'build phase marker',
                'name': 'phase1',
                'dur_list': [9.0]
            },
            'phase2': {
                'cat': 'build phase marker',
                'name': 'phase2',
                'dur_list': [0.001]
            },
        }, accum_dict)

  def test_aggregate_from_accum_dict(self):
    accum_dict = {
        'fake_name': {
            'cat': 'fake_cat',
            'name': 'fake_name',
            'dur_list': [3, 1]
        },
    }

    self.assertEqual([{
        'cat': 'fake_cat',
        'name': 'fake_name',
        'dur': 2.0
    }], lib._aggregate_from_accum_dict(accum_dict))


if __name__ == '__main__':
  unittest.main()
