#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import sys
import time

from timeit import default_timer

from proxytools.app import App
from proxytools.config import Config
from proxytools.utils import configure_logging

log = logging.getLogger()


if __name__ == '__main__':
    args = Config.get_args()
    Config.configure_logging(log)

    app = App(args)
    #app.work()
