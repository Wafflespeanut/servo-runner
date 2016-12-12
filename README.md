## servo-wpt

Servo builds experience a lot of [intermittent failures](https://github.com/servo/servo/issues?q=is%3Aissue+is%3Aopen+label%3AI-intermittent). This suite runs 24/7 in a dedicated machine, building and testing servo using the [web platform test runner](https://github.com/w3c/wptrunner). It maintains a database of `rr` recordings of every intermittent encountered in the tests, which would be helpful for people who're willing to work on those later.

### Running

Currently, this is not in a state for local usage. It requires:

 - a bot willing to work for you (see `config.json.sample`)
 - `requests` python module for communication with the Github API
 - `rr` binary built from [our fork](https://github.com/servo-automation/rr).
 - `IntermittentsDB` from the [intermittent-tracker](https://github.com/servo/intermittent-tracker/).

Run `python runner.py` to begin the siege!
