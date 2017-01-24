from watcher import IntermittentWatcher

import json, sys

if __name__ == '__main__':
    with open('config.json', 'r') as fd:
        config = json.load(fd)

    is_dummy = False
    args = ' '.join(sys.argv[1:])
    if 'subdir' in config:
        if not 'suite' in config:
            print 'Test subdirectory present in config without specific test suite to run.'
            sys.exit(1)
        subdir = config['subdir']
        suite = config['suite']
    else:
        subdir = None
        suite = None
    watcher = IntermittentWatcher(config['servo_path'], config['user'], config['token'],
                                  config['db_path'], build=config['build'], log_path=config['log'],
                                  is_dummy='--no-api' in args, branch=config['branch'],
                                  remote=config['remote'], suite=suite, subdir=subdir)
    watcher.start()
