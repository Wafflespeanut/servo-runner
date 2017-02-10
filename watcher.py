from api_provider import ServoGithubAPIProvider
from datetime import datetime

import json, os, subprocess, shutil, sys, time

RR_PATH = os.path.expanduser('~/.local/share/rr')
TEMP_LOG = '/tmp/wpt_log'
STATUS_LOG = 'status'
WPT_COMMAND = './mach test-%s --debugger=rr --debugger-args="record -S" --log-raw %s'
OUTPUT_HEAD = 'Tests with unexpected results:'
SUBTEST_PREFIX = 'Unexpected subtest result'
NOTIFICATION = ('Hey! I have a `rr` recording corresponding to this failure. '
                'Let @jdm know if you need it!')


class IntermittentWatcher(object):
    def __init__(self, upstream, clone_path, user, token, db_path, build, log_path='log.json',
                 is_dummy=False, branch='master', subdir=None, suite=None, no_update=False,
                 no_execute=False):
        self.base_clone = upstream
        self.clone_dir = clone_path
        self.api = ServoGithubAPIProvider(user, token)
        sys.path.append(os.path.join(db_path))
        from db import IntermittentsDB
        with open(os.path.join(db_path, 'intermittents.json'), 'r') as fd:
            self.db = IntermittentsDB(json.load(fd))
        self.last_updated = datetime.now().day - 1
        self.build = 'dev'
        if build == 'release':
            self.build = 'release'
        self.test = 'wpt'
        self.log_path = log_path
        self.is_dummy = is_dummy
        self.branch = branch
        self.subdir = subdir
        self.suite = suite
        self.no_update = no_update
        self.no_execute = no_execute
        if is_dummy:
            print '\033[1m\033[93mRunning in dummy mode: API will not be used!\033[0m'

        # Recreate the environment from the last successful run by changing the working
        # directory to the last clone that was made.
        status_path = os.path.join(upstream, STATUS_LOG)
        if os.path.exists(status_path):
            with open(status_path, 'r') as fd:
                contents = json.load(fd)
                os.chdir(contents['last_clone'])
        else:
            os.chdir(self.base_clone)

        if os.path.exists(log_path):
            with open(log_path, 'r') as fd:
                self.results = json.load(fd)
        else:
            self.results = {}

    def execute(self, command, suppress=False):
        out = ''
        print '\033[93m%s\033[0m' % command
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        for line in iter(proc.stdout.readline, ''):
            sys.stdout.write(line)      # print stdout/stderr lines as and whenever we get one
            sys.stdout.flush()
            out += line
        proc.wait()
        if not suppress and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, command, out)
        return out

    def log(self, msg):
        print '\033[91m%s\033[0m: \033[92m%s\033[0m' % (datetime.now(), msg)

    def run(self):
        current = {}
        self.log('Running tests...')

        if not self.no_execute:
            command = WPT_COMMAND % (self.test, TEMP_LOG)
            if self.build == 'release':
                command += ' --release'
            if self.subdir:
                command += ' %s' % self.subdir
            self.execute(command, suppress=True)

        self.log('Analyzing the raw log...')
        with open(TEMP_LOG, 'r') as fd:
            default_subtest = {'data': '', 'status': None}
            for line in fd:
                obj = json.loads(line)
                if obj['thread'] == 'MainThread':
                    continue
                if obj['action'] == 'test_start':
                    # tests running in each thread
                    current[obj['thread']] = {'test': obj['test'], 'output': ''}
                    default = {'record': None, 'issue': None, 'subtest': {}, 'notified': False}
                    self.results.setdefault(obj['test'], default)
                elif obj['action'] == 'test_end':
                    test = current[obj['thread']]['test']
                    # Only store the test's stdout if any subtests failed or the test has an
                    # unexpected result
                    if obj.get('expected') or self.results[test]['subtest']:
                        subtest_result = self.results[test]['subtest'].setdefault(test, default_subtest)
                        self.results[test]['subtest'][test]['data'] = current[obj['thread']]['output']
                elif obj['action'] == 'process_output':
                    test = current[obj['thread']]['test']
                    current[obj['thread']]['output'] += obj['data'] + '\n'
                    if obj['data'].startswith('rr: Saving'):
                        data = obj['data'].split()
                        old = self.results[test]['record']
                        new = data[-1][1:-2]        # rr-record location
                        if old and old != new:
                            self.log('Replacing existing record %r with new one %r for test %r' % \
                                     (old, new, test))
                            if os.path.exists(old):
                                shutil.rmtree(old)
                        self.results[test]['record'] = new

                # Both test_status and test_end can have an expected field indicating that an
                # unexpected result was encountered.
                if obj.get('expected'):
                    test, subtest = current[obj['thread']]['test'], obj.get('subtest', obj['test'])
                    issues = self.db.query(test)
                    if issues:
                        selected = 0
                        # When multiple issues match, we check for patterns like
                        # "Intermittent [status] in path/to/test.html" to find
                        # this most meaningful result.
                        if len(issues) > 1:
                            status = obj['status'].lower()
                            for (i, issue) in enumerate(issues):
                                if status in issue['title'].lower():
                                    selected = i
                        self.results[test]['issue'] = issues[selected]['number']
                    subtest_result = self.results[test]['subtest'].setdefault(subtest, default_subtest)
                    subtest_result['status'] = obj['status']
                    # For test_end actions there is no associated message. We have already recorded
                    # the full process output and stored it in the data field of the test results.
                    if obj['action'] == 'test_status':
                        self.results[test]['subtest'][subtest]['data'] = obj.get('message', '')

        self.log('Cleaning up recordings...')
        for test, result in list(self.results.iteritems()):
            if result['subtest']:
                if not result['notified']:
                    fn = self.post_comment if result['issue'] else self.create_issue
                    print fn(test)
                    self.results[test]['notified'] = True
            else:
                result = self.results.pop(test)
                if result['record']:
                    self.log('Removing unused record %r for test %r' % (result['record'], test))
                    if os.path.exists(result['record']):
                        shutil.rmtree(result['record'])

        with open(self.log_path, 'w') as fd:
            self.log('Dumping the test results...')
            json.dump(self.results, fd)

    def create_issue(self, test):
        self.log('Opening issue for %s...' % test)
        subtests = self.results[test]['subtest'].values()
        status = subtests[0]['status']
        title = 'Intermittent %s in %s' % (status, test)
        body = '\n\n'.join(['```'] + map(lambda r: r['data'], subtests) + ['```'] + [NOTIFICATION])
        labels = ['I-intermittent']
        if self.test == 'css':
            labels.append('A-content/css')
        args = [title, body, labels]
        return args if self.is_dummy else self.api.create_issue(*args)

    def post_comment(self, test):
        self.log('Posting comment...')
        subtests = self.results[test]['subtest'].values()
        body = '\n\n'.join(map(lambda r: '    ' + r['data'], subtests) + [NOTIFICATION])
        args = [body, self.results[test]['issue']]
        return args if self.is_dummy else self.api.post_comment(*args)

    def update(self):
        if self.no_update:
            return

        dir_name = "servo-%s" % time.strftime('%Y-%m-%d')
        new_clone = os.path.join(self.clone_dir, dir_name)
        if not os.path.exists(self.clone_dir):
            os.makedirs(self.clone_dir)

        if os.path.exists(new_clone):
            self.log('Using existing clone...')
            return

        self.log('Updating upstream...')
        self.execute('git clone %s %s' % (self.base_clone, new_clone))
        os.chdir(new_clone)
        self.execute('git remote add upstream https://github.com/servo/servo.git')
        self.execute('git checkout master')
        self.execute('git pull upstream master')
        self.execute('git rebase master remotes/origin/%s' % self.branch)
        self.log('Building in %s mode...' % self.build)
        self.execute('./mach build --%s' % self.build)

        with open(os.path.join(self.base_clone, STATUS_LOG), 'wb') as fd:
            self.log('Logging the latest clone directory (%s)' % new_clone)
            json.dump({"last_clone": new_clone}, fd)

    def start(self):
        while True:
            cur_time = datetime.now()
            if cur_time.hour >= 0 and cur_time.day > self.last_updated:
                self.update()
                self.last_updated = cur_time.day
            self.run()
            if self.no_execute:
                return
            if not self.suite:
                self.test = 'wpt' if self.test == 'css' else 'css'
