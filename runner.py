from watcher import IntermittentWatcher

import json, sys

if __name__ == '__main__':
    with open('config.json', 'r') as fd:
        config = json.load(fd)

    is_dummy = False
    args = ' '.join(sys.argv[1:])
    watcher = IntermittentWatcher(config['servo_path'], config['user'], config['token'],
                                  config['db_path'], build=config['build'], log_path=config['log'],
                                  is_dummy='--no-api' in args)
    watcher.start()
