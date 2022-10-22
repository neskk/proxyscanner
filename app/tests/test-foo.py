#!/usr/bin/python
# -*- coding: utf-8 -*-

class Foo(object):
  def bar(self):
    print type(self).__name__

class SubFoo(Foo):
  pass

SubFoo().bar()