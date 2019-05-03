# Copyright 2015 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import json
import unittest

import mock

from dashboard import auto_bisect
from dashboard.common import namespaced_stored_object
from dashboard.common import testing_common
from dashboard.common import utils
from dashboard.models import anomaly


class StartNewBisectForBugTest(testing_common.TestCase):

  def setUp(self):
    super(StartNewBisectForBugTest, self).setUp()
    self.SetCurrentUser('internal@chromium.org')
    namespaced_stored_object.Set('bot_configurations', {
        'linux-pinpoint': {},
    })

  def testStartNewBisectForBug_UnbisectableTest_ReturnsError(self):
    testing_common.AddTests(['Sizes'], ['x86'], {'sizes': {'abcd': {}}})
    # The test suite "sizes" is in the black-list of test suite names.
    test_key = utils.TestKey('Sizes/x86/sizes/abcd')
    anomaly.Anomaly(
        bug_id=444, test=test_key,
        start_revision=155000, end_revision=155100,
        median_before_anomaly=100, median_after_anomaly=200).put()
    result = auto_bisect.StartNewBisectForBug(444)
    self.assertEqual({'error': 'Could not select a test.'}, result)

  @mock.patch.object(
      utils, 'IsValidSheriffUser', mock.MagicMock(return_value=True))
  @mock.patch.object(
      auto_bisect.pinpoint_service, 'NewJob')
  @mock.patch.object(
      auto_bisect.start_try_job, 'GuessStoryFilter')
  @mock.patch.object(auto_bisect.pinpoint_request, 'ResolveToGitHash',
                     mock.MagicMock(return_value='abc123'))
  def testStartNewBisectForBug_Pinpoint_Succeeds(self, mock_guess, mock_new):
    namespaced_stored_object.Set('bot_configurations', {
        'linux-pinpoint': {
            'dimensions': [{'key': 'foo', 'value': 'bar'}]
        },
    })

    namespaced_stored_object.Set('repositories', {
        'chromium': {'some': 'params'},
    })

    mock_new.return_value = {'jobId': 123, 'jobUrl': 'http://pinpoint/123'}

    testing_common.AddTests(
        ['ChromiumPerf'], ['linux-pinpoint'], {'sunspider': {'score': {}}})
    test_key = utils.TestKey('ChromiumPerf/linux-pinpoint/sunspider/score')
    testing_common.AddRows(
        'ChromiumPerf/linux-pinpoint/sunspider/score',
        {
            11999: {
                'a_default_rev': 'r_chromium',
                'r_chromium': '9e29b5bcd08357155b2859f87227d50ed60cf857'
            },
            12500: {
                'a_default_rev': 'r_chromium',
                'r_chromium': 'fc34e5346446854637311ad7793a95d56e314042'
            }
        })
    a = anomaly.Anomaly(
        bug_id=333, test=test_key,
        start_revision=12000, end_revision=12500,
        median_before_anomaly=100, median_after_anomaly=200).put()
    result = auto_bisect.StartNewBisectForBug(333)
    self.assertEqual(
        {'issue_id': 123, 'issue_url': 'http://pinpoint/123'}, result)
    mock_guess.assert_called_once_with(
        'ChromiumPerf/linux-pinpoint/sunspider/score')
    self.assertEqual('123', a.get().pinpoint_bisects[0])
    self.assertEqual(
        {'alert': a.urlsafe(), 'test_path': test_key.id()},
        json.loads(mock_new.call_args[0][0]['tags']))
    anomaly_entity = a.get()
    anomaly_magnitude = (anomaly_entity.median_after_anomaly -
                         anomaly_entity.median_before_anomaly)
    self.assertEqual(
        anomaly_magnitude,
        mock_new.call_args[0][0]['comparison_magnitude'])

  @mock.patch.object(
      auto_bisect.pinpoint_request, 'PinpointParamsFromBisectParams',
      mock.MagicMock(
          side_effect=auto_bisect.pinpoint_request.InvalidParamsError(
              'Some reason')))
  def testStartNewBisectForBug_Pinpoint_ParamsRaisesError(self):
    testing_common.AddTests(
        ['ChromiumPerf'], ['linux-pinpoint'], {'sunspider': {'score': {}}})
    test_key = utils.TestKey('ChromiumPerf/linux-pinpoint/sunspider/score')
    testing_common.AddRows(
        'ChromiumPerf/linux-pinpoint/sunspider/score',
        {
            11999: {
                'r_foo': '9e29b5bcd08357155b2859f87227d50ed60cf857'
            },
            12500: {
                'r_foo': 'fc34e5346446854637311ad7793a95d56e314042'
            }
        })
    anomaly.Anomaly(
        bug_id=333, test=test_key,
        start_revision=12000, end_revision=12501,
        median_before_anomaly=100, median_after_anomaly=200).put()
    result = auto_bisect.StartNewBisectForBug(333)
    self.assertEqual(
        {'error': 'Some reason'}, result)

  def testStartNewBisectForBug_BlacklistedMaster_RaisesError(self):
    # Same setup as testStartNewBisectForBug_Pinpoint_Succeeds except for this
    # one setting.
    namespaced_stored_object.Set(
        'file_bug_bisect_blacklist', {'ChromiumPerf': []})
    namespaced_stored_object.Set('bot_configurations', {
        'linux-pinpoint': {
            'dimensions': [{'key': 'foo', 'value': 'bar'}]
        },
    })

    namespaced_stored_object.Set('repositories', {
        'chromium': {'some': 'params'},
    })

    testing_common.AddTests(
        ['ChromiumPerf'], ['linux-pinpoint'], {'sunspider': {'score': {}}})
    test_key = utils.TestKey('ChromiumPerf/linux-pinpoint/sunspider/score')
    testing_common.AddRows(
        'ChromiumPerf/linux-pinpoint/sunspider/score',
        {
            11999: {
                'a_default_rev': 'r_chromium',
                'r_chromium': '9e29b5bcd08357155b2859f87227d50ed60cf857'
            },
            12500: {
                'a_default_rev': 'r_chromium',
                'r_chromium': 'fc34e5346446854637311ad7793a95d56e314042'
            }
        })
    anomaly.Anomaly(
        bug_id=333, test=test_key,
        start_revision=12000, end_revision=12500,
        median_before_anomaly=100, median_after_anomaly=200).put()
    result = auto_bisect.StartNewBisectForBug(333)
    self.assertIn('error', result)
    self.assertIn(
        'only available masters are blacklisted from automatic bisects',
        result['error'])

  @mock.patch.object(
      utils, 'IsValidSheriffUser', mock.MagicMock(return_value=True))
  @mock.patch.object(
      auto_bisect.pinpoint_service, 'NewJob')
  @mock.patch.object(
      auto_bisect.start_try_job, 'GuessStoryFilter')
  @mock.patch.object(auto_bisect.pinpoint_request, 'ResolveToGitHash',
                     mock.MagicMock(return_value='abc123'))
  def testStartNewBisectForBut_BlacklistedMaster_SucceedsIfAlternative(
      self, _, mock_new):
    # Even if there are blacklisted masters, the bisect request should still
    # succeed if there's a non-blacklisted master.
    namespaced_stored_object.Set(
        'file_bug_bisect_blacklist', {'ChromiumPerf': []})
    namespaced_stored_object.Set('bot_configurations', {
        'linux-pinpoint': {
            'dimensions': [{'key': 'foo', 'value': 'bar'}]
        },
    })

    namespaced_stored_object.Set('repositories', {
        'chromium': {'some': 'params'},
    })

    mock_new.return_value = {'jobId': 123, 'jobUrl': 'http://pinpoint/123'}

    testing_common.AddTests(
        ['ChromiumPerf'], ['linux-pinpoint'], {'sunspider': {'score': {}}})
    testing_common.AddTests(
        ['ChromiumPerf2'], ['linux-pinpoint'], {'sunspider': {'score': {}}})
    test_key = utils.TestKey('ChromiumPerf/linux-pinpoint/sunspider/score')
    test_key2 = utils.TestKey('ChromiumPerf2/linux-pinpoint/sunspider/score')
    rows = {
        11999: {
            'a_default_rev': 'r_chromium',
            'r_chromium': '9e29b5bcd08357155b2859f87227d50ed60cf857'
        },
        12500: {
            'a_default_rev': 'r_chromium',
            'r_chromium': 'fc34e5346446854637311ad7793a95d56e314042'
        }
    }
    testing_common.AddRows('ChromiumPerf/linux-pinpoint/sunspider/score', rows)
    testing_common.AddRows('ChromiumPerf2/linux-pinpoint/sunspider/score', rows)
    anomaly.Anomaly(
        bug_id=333, test=test_key,
        start_revision=12000, end_revision=12500,
        median_before_anomaly=100, median_after_anomaly=200).put()
    a = anomaly.Anomaly(
        bug_id=333, test=test_key2,
        start_revision=12000, end_revision=12500,
        median_before_anomaly=100, median_after_anomaly=200).put()
    result = auto_bisect.StartNewBisectForBug(333)
    self.assertNotIn('error', result)
    self.assertEqual(
        {'alert': a.urlsafe(), 'test_path': test_key2.id()},
        json.loads(mock_new.call_args[0][0]['tags']))

if __name__ == '__main__':
  unittest.main()
