#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from proxytools.app import App
from proxytools.config import Config
from proxytools.utils import configure_logging

log = logging.getLogger()


if __name__ == '__main__':
    args = Config.get_args()
    configure_logging(log, args.verbose, args.log_path, "-proxyscanner")

    app = App()
    app.start()
