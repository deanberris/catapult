import httplib2
import json
from oauth2client import client
from oauth2client import service_account # pylint: disable=no-name-in-module
import time
import urllib


class PerfDashboardCommunicator(object):

  REQUEST_URL = 'https://chromeperf.appspot.com/api/'
  OAUTH_CLIENT_ID = (
      '62121018386-h08uiaftreu4dr3c4alh3l7mogskvb7i.apps.googleusercontent.com')
  OAUTH_CLIENT_SECRET = 'vc1fZfV1cZC6mgDSHV-KSPOz'
  SCOPES = 'https://www.googleapis.com/auth/userinfo.email'

  def __init__(self, json_key_path=None, auto_authorize=True):
    self._json_key_path = json_key_path
    self._connection = None
    if auto_authorize:
      self._connection = self.AuthorizeAccount()

  def AuthorizeAccount(self):
    """A factory for authorized account credentials."""
    if self._json_key_path:
      try:
        return self._AuthorizeAccountServiceAccount(self._json_key_path)
      except Exception:  # pylint: disable=broad-except
        print ('Failure authenticating with service account. Falling back to '
               'user authentication.')
    return self._AuthorizeAccountUserAccount()

  def _AuthorizeAccountServiceAccount(self, json_key):
    """Used to create a service account connection with the dashboard.

    args:
      json_key: Path to json file that contains credentials.
    returns:
      An object that can be used to communicate with the dashboard.
    """
    creds = service_account.ServiceAccountCredentials.from_json_keyfile_name(
        json_key, [self.SCOPES])
    return creds.authorize(httplib2.Http())

  def _AuthorizeAccountUserAccount(self):
    """Used to create an user account connection with the performance dashboard.

    returns:
      An object that can be used to communicate with the dashboard.
    """
    flow = client.OAuth2WebServerFlow(
        self.OAUTH_CLIENT_ID, self.OAUTH_CLIENT_SECRET, [self.SCOPES],
        approval_prompt='force')
    flow.redirect_uri = client.OOB_CALLBACK_URN
    print('Go to the followinhg link in your browser:\n'
          '    %s\n' % flow.step1_get_authorize_url())
    code = raw_input('Enter verification code: ').strip()
    try:
      creds = flow.step2_exchange(code)
      return creds.authorize(httplib2.Http())
    except client.FlowExchangeError:
      print 'User authentication has failed.'
      raise

  def _MakeApiRequest(self, request, retry=3, delay=3):
    """Used to communicate with perf dashboard.

    args:
      credentials: Set of credentials generated by
      request: String that contains POST request to dashboard.
    returns:
      Contents of the response from the dashboard.
    """
    assert self._connection, 'Must start conection before making request.'
    print 'Making API request: %s' % request
    resp, content = self._connection.request(
        self.REQUEST_URL + request,
        method="POST",
        headers={'Content-length': 0})
    if resp['status'] != '200':
      print ('Response: %s\nContent: %s\nError detected while making api '
             'request. Returned: %s' % (resp, content, resp['status']))
      if retry:
        print ('Retrying command after %s seconds. %s retries left...'
               % (delay, retry - 1))
        time.sleep(delay)
        return self._MakeApiRequest(request, retry=retry-1, delay=delay*2)
    return  json.loads(content)

  def ListTestPaths(self, benchmark, sheriff=False):
    """Lists test paths for the given benchmark.

    args:
      benchmark: Benchmark to get paths for.
      sheriff:
          Filters test paths to only ones monitored by the given sheriff
          rotation.
    returns:
      A list of test paths. Ex. ['TestPath1', 'TestPath2']
    """
    r = 'list_timeseries/%s' % benchmark
    if sheriff:
      r += '?sheriff=%s' % sheriff
    return self._MakeApiRequest(r)

  def GetTimeseries(self, test_path, days=30):
    """Get timeseries for the given test path.

    args:
      test_path: test path to get timeseries for.
      days: Number of days to get data points for.
    returns:
      A dict in the format:
      {'revision_logs':{
          r_commit_pos: {... data ...},
          r_chromium_rev: {... data ...},
          ...},
       'timeseries': [
           [revision, value, timestamp, r_commit_pos, r_webkit_rev],
           ...
           ],
       'test_path': test_path}
    """
    options = urllib.urlencode({'num_days': days})
    r = 'timeseries/%s?%s' % (urllib.quote_plus(test_path), options)
    return self._MakeApiRequest(r)

  def GetBugData(self, bug_id):
    """Returns data on the given bug."""
    return self._MakeApiRequest('bugs/%d' % bug_id)

  def GetAlertData(self, benchmark, days=30):
    """Returns alerts for the given benchmark."""
    options = urllib.urlencode({'benchmark': benchmark})
    return self._MakeApiRequest('alerts/history/%d?%s' % (days, options))
