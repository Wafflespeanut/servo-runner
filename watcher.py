
from datetime import datetime

import json, os, subprocess, shutil, sys

RR_PATH = os.path.expanduser('~/.local/share/rr')
TEMP_LOG = '/tmp/wpt_log'
WPT_ARROW = '\xe2\x96\xb6'
WPT_COMMAND = './mach test-wpt %s --debugger=rr --debugger-args=record --no-pause --log-raw %s' \
              % ('tests/wpt/web-platform-tests/dom/events/Event-dispatch-click.html', TEMP_LOG)
OUTPUT_OFFSET = 'Tests with unexpected results:'

class IntermittentWatcher(object):
    def __init__(self, upstream, build='debug'):
        self.last_updated = datetime.now().day - 1
        self.build = build
        self.upstream = upstream
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
        results, expectations = {}, {}
        current = {}
        command = WPT_COMMAND
        if self.build == 'release':
            command += ' --release'
        out = self.execute(command)
        out = out[(out.find(OUTPUT_OFFSET) + len(OUTPUT_OFFSET)):-1]

        with open(TEMP_LOG, 'r') as fd:
            for line in fd:
                obj = json.loads(line)
                if obj['thread'] == 'MainThread':
                    continue
                if obj['action'] == 'test_start':
                    current[obj['thread']] = obj['test']
                    results.setdefault(obj['test'], {'record': None, 'issue': None, 'data': ''})
                elif obj['action'] == 'process_output':
                    test = current[obj['thread']]
                    if obj['data'].startswith('rr: Saving'):
                        data = obj['data'].split()
                        results[test]['record'] = data[-1][1:-2]
                if obj.get('expected'):
                    test = current[obj['thread']]
                    expectations[test] = (obj['status'], obj['expected'])

        self.log('Cleaning up unused records...')
        for test in results:
            if not expectations.get(test):
                shutil.rmtree(results[test]['record'])

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
