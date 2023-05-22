# Official Relink Server Software
[![forthebadge](https://forthebadge.com/images/badges/powered-by-electricity.svg)](https://forthebadge.com) [![forthebadge](https://forthebadge.com/images/badges/made-with-python.svg)](https://forthebadge.com) [![forthebadge](https://forthebadge.com/images/badges/contains-tasty-spaghetti-code.svg)](https://forthebadge.com)

This is the official server software for the Relink chat service.

## Configuration:
The server can be configured by providing the environment variables documented in the `.env.example` file. You can either provide these in the environment directly, or by providing a `.env` file, such as by modifying and renaming the example file.

You will also need to provide an empty users.json file, which will be used to store user data. This file should be located in a folder called db, in the same directory as the server.py file.

### SRV DNS Records:
All clients (should) look for a SRV DNS record before connecting.

The record should be formatted as the following: `_relink._websocket.example.com.` with a response formatted as: `WEIGHT PORT example.com` of course with example.com replaced with your domain name.

For example, the `relink.network` homeserver has the record set up like this:

HOST: `	_relink._websocket.relink.network` ANSWER: `0 8765 server.relink.network`
## Proxy Support:
Due to [WS#364](https://github.com/python-websockets/websockets/issues/364) and [WS#475](https://github.com/python-websockets/websockets/issues/475),
federation to other servers will be unavailable if your server is running under a proxy.

## Submodule note:
This repository has git submodules, to clone them, use the `--recurse-submodules` flag, or run `git submodule update --init --recursive` after cloning.

## Setup:
You will need python 3.10 or newer to run this server.

You can then install the required dependencies by running `pip install -r requirements.txt`.
