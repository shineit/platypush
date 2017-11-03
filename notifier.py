#!/usr/bin/env python

import functools
import importlib
import os
import logging
import json
import socket
import subprocess
import sys
import time
import websocket
import yaml

from threading import Thread
from getopt import getopt

__author__ = 'Fabio Manganiello <info@fabiomanganiello.com>'

#-----------#

curdir = os.path.dirname(os.path.realpath(__file__))
lib_dir = curdir + os.sep + 'lib'
sys.path.insert(0, lib_dir)

config_file = curdir + os.sep + 'config.yaml'
config = {}
with open(config_file,'r') as f:
    config = yaml.load(f)

API_KEY = config['pushbullet_token']
DEVICE_ID = config['device_id'] \
    if 'device_id' in config else socket.gethostname()

DEBUG = config['debug'] if 'debug' in config else False

modules = {}
plugins = {}


def on_open(ws):
    logging.info('Connection opened')


def on_close(ws):
    logging.info('Connection closed')


def on_error(ws, error):
    logging.error(error)


def _exec_func(body):
    module_name = 'plugins.{}'.format(body['plugin'])
    if module_name in modules:
        module = modules[module_name]
    else:
        try:
            module = importlib.import_module(module_name)
            modules[module_name] = module
        except ModuleNotFoundError as e:
            logging.warn('No such plugin: {}'.format(body['plugin']))
            return

    logging.info('Received push addressed to me: {}'.format(body))

    args = body['args'] if 'args' in body else {}
    cls_name = functools.reduce(
        lambda a,b: a.title() + b.title(),
        (body['plugin'].title().split('.'))
    ) + 'Plugin'

    if cls_name in plugins:
        instance = plugins[cls_name]
    else:
        cls = getattr(module, cls_name)
        instance = cls()
        plugins[cls_name] = cls

    out, err = instance.run(args)

    logging.info('Command output: {}'.format(out))
    if err:
        logging.warn('Command error: {}'.format(err))


def _on_push(ws, data):
    data = json.loads(data)
    if data['type'] == 'tickle' and data['subtype'] == 'push':
        logging.debug('Received push tickle')
        return

    if data['type'] != 'push':
        return  # Not a push notification

    push = data['push']
    logging.debug('Received push: {}'.format(push))

    if 'body' not in push:
        return

    body = push['body']
    try:
        body = json.loads(body)
    except ValueError as e:
        return

    if 'target' not in body or body['target'] != DEVICE_ID:
        return  # Not for me

    if 'plugin' not in body:
        return  # No plugin specified

    thread = Thread(target=_exec_func, args=(body,))
    thread.start()

def on_push(ws, data):
    try:
        _on_push(ws, data)
    except Exception as e:
        on_error(ws, e)


def main():
    DEBUG = False
    config_file = curdir + os.sep + 'config.yaml'

    optlist, args = getopt(sys.argv[1:], 'vh')
    for opt, arg in optlist:
        if opt == '-c':
            config_file = arg
        if opt == '-v':
            DEBUG = True
        elif opt == '-h':
            print('''
Usage: {} [-v] [-h] [-c <config_file>]
    -v  Enable debug mode
    -h  Show this help
    -c  Path to the configuration file (default: ./config.yaml)
'''.format(sys.argv[0]))
            return

    config = {}
    with open(config_file,'r') as f:
        config = yaml.load(f)

    API_KEY = config['pushbullet_token']
    DEVICE_ID = config['device_id'] \
        if 'device_id' in config else socket.gethostname()

    if 'debug' in config:
        DEBUG = config['debug']

    if DEBUG:
        logging.basicConfig(level=logging.DEBUG)
        websocket.enableTrace(True)
    else:
        logging.basicConfig(level=logging.INFO)

    ws = websocket.WebSocketApp('wss://stream.pushbullet.com/websocket/' +
                                API_KEY,
                                on_message = on_push,
                                on_error = on_error,
                                on_close = on_close)
    ws.on_open = on_open
    ws.run_forever()


if __name__ == '__main__':
    main()

