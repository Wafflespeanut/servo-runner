from StringIO import StringIO
from base64 import standard_b64encode as b64_encode
from gzip import GzipFile

import json, requests


class ServoGithubAPIProvider(object):
    base_url = 'https://api.github.com/repos/servo/servo'
    new_issue_url = base_url + '/issues'
    issue_url = base_url + '/issues/%s/'
    comments_post_url = issue_url + 'comments'

    def __init__(self, user, token):
        self.user = user
        self.token = token

    def _request(self, method, url, data=None):
        authorization = '%s:%s' % (self.user, self.token)
        base64 = b64_encode(authorization).replace('\n', '')
        headers = { 'Authorization': 'Basic %s' % base64 }

        if data:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data)

        req_method = getattr(requests, method.lower())
        resp = req_method(url, data=data, headers=headers)
        data, code = resp.text, resp.status_code

        if code < 200 or code >= 300:
            print 'Got a %s response: %r' % (code, data)
            raise Exception

        if resp.headers.get('Content-Encoding') == 'gzip':
            fd = GzipFile(fileobj=StringIO(data))
            data = fd.read()
        return (resp.headers, json.loads(data))

    def post_comment(self, comment, issue_number):
        url = self.comments_post_url % issue_number
        _headers, body = self._request('POST', url, {'body': comment})
        return body

    def create_issue(self, title, body, labels=[]):
        content = {'title': title, 'body': body, 'labels': labels}
        _headers, body = self._request('POST', self.new_issue_url, content)
        return body
