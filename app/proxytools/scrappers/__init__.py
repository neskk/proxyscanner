#!/usr/bin/python
# -*- coding: utf-8 -*-

from inspect import isclass
from pkgutil import iter_modules
from pathlib import Path
from importlib import import_module


__all__ = [
    'FileReader',
    'Freeproxylist',
    'GeoNodeHTTP',
    'GeoNodeSOCKS4',
    'GeoNodeSOCKS5',
    # 'Idcloak',
    'OpenProxyHTTP',
    'OpenProxySOCKS4',
    'OpenProxySOCKS5',
    'Premproxy',
    'ProxyNova',
    'ProxyScrapeHTTP',
    'ProxyScrapeSOCKS4',
    'ProxyScrapeSOCKS5',
    # 'Proxyserverlist24',
    # 'Sockslist',
    'Socksproxy',
    # 'Socksproxylist24',
    'SpysHTTPS',
    'SpysSOCKS',
    'TheSpeedXHTTP',
    'TheSpeedXSOCKS4',
    'TheSpeedXSOCKS5',
    # 'Vipsocks24'
]

CLASSES = []

# https://julienharbulot.com/python-dynamical-import.html
# Iterate through the modules in the current package
package_dir = Path(__file__).resolve().parent
for (_, module_name, _) in iter_modules([package_dir]):

    # Import the module and iterate through its attributes
    module = import_module(f"{__name__}.{module_name}")
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)

        if isclass(attribute) and attribute_name in __all__:
            # Add the class to this package's variables
            globals()[attribute_name] = attribute
            CLASSES.append(attribute)
