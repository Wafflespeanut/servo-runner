
from flask import Flask, abort, request
from hashlib import sha1

from api_provider import GithubAPIProvider

import hmac, os, json, random


# Implementation of digest comparison from Django
# https://github.com/django/django/blob/0ed7d155635da9f79d4dd67e4889087d3673c6da/django/utils/crypto.py#L96-L105
def compare_digest(val_1, val_2):
    result = 0
    if len(val_1) != len(val_2):
        return False

    for x, y in zip(val_1, val_2):
        result |= ord(x) ^ ord(y)

    return result == 0


if __name__ == '__main__':
    # app "secret" key is optional, but it makes sure that you're getting payloads from
    # Github. If a third-party found your POST URL, then anyone can send a cooked-up payload,
    # and your bot will respond to it. In python, you can do something like,
    # `print ''.join(map(chr, random.sample(range(32, 127), 32)))`
    # (which will generate a 32-byte key in the ASCII range)

    app = Flask('servo-runner')
    with open('config.json', 'r') as fd:
        config = json.load(fd)

    choice = random.choice(config['logins'])    # pseudo-random choice of bot
    user = choice['user']
    auth_token = choice['token']
    secret = str(config.get('secret'))


    @app.route('/', methods=['POST'])
    def handle_payload():
        try:
            raw_payload = request.data
            payload = json.loads(raw_payload)
        except:
            abort(400)

        # if we have the event in the header, then run only those handlers corresponding to that event
        event_name = request.headers.get('X-GitHub-Event')
        verify_msg = "Payload's signature can't be verified without the secret key!"

        if secret:
            header_sign = request.headers.get('X-Hub-Signature', '') + '='
            _hash_function, signature = header_sign.split('=')[:2]
            msg_auth_code = hmac.new(secret, raw_payload, sha1)
            hashed = msg_auth_code.hexdigest()

            verify_msg = "Payload's signature has been verified!"
            if not compare_digest(signature, hashed):
                print 'Invalid signature!'
                abort(403)

        print verify_msg

        api = GithubAPIProvider(payload, user, auth_token)
        # run stuff

        return 'Yay!', 200


    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
