from watcher import IntermittentWatcher

import json

if __name__ == '__main__':
    with open('config.json', 'r') as fd:
        config = json.load(fd)

    watcher = IntermittentWatcher(config['servo_path'], config['user'], config['token'],
                                  config['db_path'], build=config['build'], log_path=config['log'])
    watcher.start()
