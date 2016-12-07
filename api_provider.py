from StringIO import StringIO
from base64 import standard_b64encode as b64_encode
from gzip import GzipFile

import contextlib, json, re, requests, urllib2


class APIProvider(object):
    def __init__(self, payload):
        self.payload = payload

        node = self.get_matching_path(['owner', 'login'])
        self.owner = node['owner']['login'].lower()
        self.repo = node['name'].lower()

        node = self.get_matching_path(['number'])
        self.issue_number = node.get('number')

    def get_matching_path(self, matches):   # making the helper available for handlers
        '''
        Recursively traverse through the dictionary to find a matching path.
        Once that's found, get the parent key which triggered that match.

        >>> d = {'a': {'b': {'c': {'d': 1}, {'e': 2}}}}
        >>> node = get_path_parent(d, ['c', 'e'])
        >>> print node
        {'c': {'e': 2, 'd': 1}}
        >>> node['c']['e']
        2

        It returns the (parent) node on which we can call those matching keys. This is
        useful when we're sure about how a path of a leaf ends, but not how it begins.

        An optional method specifies how to address the object i.e., whether to do it
        directly, or call another method to get the underlying object from the wrapper.
        (the method is overridden when we use JsonCleaner's NodeMarker type)
        '''
        sep = '->'
        if not match:
            return

        def get_path(item, match_path, path=''):
            if hasattr(item, '__iter__'):
                iterator = xrange(len(item)) if isinstance(item, list) else item
                for key in iterator:
                    new_path = path + str(key) + sep
                    if new_path.endswith(match_path):
                        return new_path.rstrip(sep)

                    result = get_path(item[key], match_path, new_path)
                    if result:
                        return result

        match_path = sep.join(match) + sep
        result = get_path(self.payload, match_path)
        if not result:      # so that we don't return None
            return {}

        keys = result.split(sep)[:-len(match)]
        if not keys:        # special case - where the path is a prefix
            return self.payload

        parent = keys.pop(0)
        node = self.payload[parent]

        for child in keys:      # start from the root and get the parent
            node = node[child]

        return node

    def post_comment(self, comment):
        raise NotImplementedError


class GithubAPIProvider(APIProvider):
    base_url = 'https://api.github.com/repos/'
    issue_url = base_url + '%s/%s/issues/%s/'
    comments_post_url = issue_url + 'comments'

    def __init__(self, payload, user, token):
        self.user = user
        self.token = token
        super(GithubAPIProvider, self).__init__(payload)

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

    def post_comment(self, comment):
        url = self.comments_post_url % (self.owner, self.repo, self.issue_number)
        self._request('POST', url, {'body': comment})
