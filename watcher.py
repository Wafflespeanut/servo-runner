
from datetime import datetime

import json, os, subprocess, shutil, sys

RR_PATH = os.path.expanduser('~/.local/share/rr')
TEMP_LOG = '/tmp/wpt_log'
# WPT_COMMAND = './mach test-%s tests/wpt/web-platform-tests/dom/events/Event-dispatch-click.html --debugger=rr --debugger-args=record --no-pause --log-raw %s'
WPT_COMMAND = './mach test-%s tests/wpt/css-tests/css21_dev/html4/abs-pos-non-replaced-vlr-051.htm --debugger=rr --debugger-args=record --no-pause --log-raw %s'
OUTPUT_HEAD = 'Tests with unexpected results:'
SUBTEST_PREFIX = 'Unexpected subtest result'


class IntermittentWatcher(object):
    def __init__(self, upstream, test='css', build='debug'):
        self.last_updated = datetime.now().day - 1
        self.build = build
        self.upstream = upstream
        self.test = test
        os.chdir(self.upstream)

    def execute(self, command, call= lambda l: sys.stdout.write(l) and sys.stdout.flush()):
        out = ''
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        for line in iter(proc.stdout.readline, ''):
            call(line)
            out += line
        proc.wait()
        return out

    def log(self, msg):
        print '\033[91m%s\033[0m: \033[92m%s\033[0m' % (datetime.now(), msg)

    def run(self):
        results, current = {}, {}
        command = WPT_COMMAND % (self.test, TEMP_LOG)
        if self.build == 'release':
            command += ' --release'
        out = self.execute(command)
        out = out[(out.find(OUTPUT_HEAD) + len(OUTPUT_HEAD)):-1].strip()

        with open(TEMP_LOG, 'r') as fd:
            for line in fd:
                obj = json.loads(line)
                if obj['thread'] == 'MainThread':
                    continue
                if obj['action'] == 'test_start':
                    current[obj['thread']] = obj['test']
                    results.setdefault(obj['test'], {'record': None, 'issue': None, 'subtest': {}})
                elif obj['action'] == 'process_output':
                    test = current[obj['thread']]
                    if obj['data'].startswith('rr: Saving'):
                        data = obj['data'].split()
                        results[test]['record'] = data[-1][1:-2]
                if obj.get('expected'):
                    test, subtest = current[obj['thread']], obj.get('subtest', obj['test'])
                    results[test]['subtest'][subtest] = {'data': '', 'status': obj['status']}

        for result in map(str.strip, out.split('\n\n')):
            data = result.splitlines()
            name = data[0][data[0].find('/'):]
            if SUBTEST_PREFIX in result:
                test = name[:-1]
                subtest = data[1][(data[1].find(']') + 2):]
                results[test]['subtest'][subtest]['data'] = result
            else:
                test, subtest = name, name
                results[test]['subtest'][subtest]['data'] = result

        self.log('Cleaning up...')
        for test in results:
            if not results[test]['subtest']:
                t = results.pop(test)
                self.log('Removing unused record %r for test %r' % (t['record'], test))
                shutil.rmtree(t['record'])

        print results

    def update(self):
        self.log('Updating upstream...')
        self.execute('git pull upstream master')
        self.log('Building in %s mode...' % self.build)
        self.execute('./mach build --%s' % self.build)

    def start(self):
        while True:
            cur_time = datetime.now()
            if cur_time.hour >= 0 and cur_time.day > self.last_updated:
                # self.update()
                self.last_updated = cur_time.day
                self.log('Running tests...')
            self.run()
            exit()
