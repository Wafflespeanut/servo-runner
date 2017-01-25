from api_provider import ServoGithubAPIProvider
from datetime import datetime

import json, os, subprocess, shutil, sys, time

RR_PATH = os.path.expanduser('~/.local/share/rr')
TEMP_LOG = '/tmp/wpt_log'
STDOUT_LOG = 'stdout'
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

        stdout_log = os.path.join(self.base_clone, STDOUT_LOG)

        if self.no_execute:
            with open(stdout_log, 'rb') as f:
                out = f.read()
        else:
            command = WPT_COMMAND % (self.test, TEMP_LOG)
            if self.build == 'release':
                command += ' --release'
            if self.subdir:
                command += ' %s' % self.subdir
            out = self.execute(command, suppress=True)
            with open(stdout_log, 'wb') as f:
                f.write(out)

        if out.find(OUTPUT_HEAD) == -1:
            out = ''
        else:
            out = out[(out.find(OUTPUT_HEAD) + len(OUTPUT_HEAD)):-1].strip()

        self.log('Analyzing the raw log...')
        with open(TEMP_LOG, 'r') as fd:
            for line in fd:
                obj = json.loads(line)
                if obj['thread'] == 'MainThread':
                    continue
                if obj['action'] == 'test_start':
                    current[obj['thread']] = obj['test']    # tests running in each thread
                    default = {'record': None, 'issue': None, 'subtest': {}, 'notified': False}
                    self.results.setdefault(obj['test'], default)
                elif obj['action'] == 'process_output':
                    test = current[obj['thread']]
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
                if obj.get('expected'):     # there's an unexpected result
                    test, subtest = current[obj['thread']], obj.get('subtest', obj['test'])
                    issues = self.db.query(test)
                    if issues:      # since we're querying by name, we'll always get either one or none
                        self.results[test]['issue'] = issues[0]['number']
                    self.results[test]['subtest'][subtest] = {'data': '', 'status': obj['status']}

        self.log('Analyzing stdout...')
        for result in map(str.strip, out.split('\n\n')):
            if not result:
                continue
            data = result.splitlines()
            name = data[0][data[0].find('/'):]
            if SUBTEST_PREFIX in result:
                test = name[:-1]    # strip out the colon
                subtest = data[1][(data[1].find(']') + 2):]     # get the subtest name
            else:
                test, subtest = name, name      # tests without subtests
            self.results[test]['subtest'][subtest]['data'] = result

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
        self.log('Opening issue...')
        subtests = self.results[test]['subtest'].values()
        status = subtests[0]['status']
        title = 'Intermittent %s in %s' % (status, self.results[test])
        body = '\n\n'.join(map(lambda r: '    ' + r['data'], subtests) + [NOTIFICATION])
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
