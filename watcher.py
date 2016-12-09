
from datetime import datetime

import json, os, subprocess, sys

WPT_RESULT_ARROW = '\xe2\x96\xb6'

class IntermittentWatcher(object):
    def __init__(self, upstream, build='debug'):
        self.upstream = upstream
        os.chdir(self.upstream)

    def run(self):

        proc = subprocess.Popen('./mach test-wpt --debugger=rr --debugger-args=record --no-pause --log-raw -',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        for line in iter(process.stdout.readline, ''):
            obj = json.loads(line)
            # parse log

    def update(self):
        print '%s: Updating upstream...' % datetime.now()
        proc = subprocess.Popen('git pull upstream master', stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=True)
        proc.wait()
        print '%s: Building in %s mode...' % self.build
        proc = subprocess.Popen('./mach build -d', stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=True)
        proc.wait()

    def start(self):
        while True:
            cur_time = datetime.now()
            if cur_time.hour >= 0 and cur_time.day > self.last_updated:
                self.update()
                self.last_updated = cur_time.day
                print '%s: Running tests...' % cur_time
            self.run()
