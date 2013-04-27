# -*- Mode: Python -*-

# utility functions for building regular expressions

def OR (*args):
    return '(?:' + '|'.join (args) + ')'

def CONCAT (*args):
    return '(?:' + ''.join (args) + ')'

def NTIMES (arg, l, h):
    return '(?:' + arg + '){%d,%d}' % (l, h)

def OPTIONAL (*args):
    return '(?:' + CONCAT(*args) + ')?'

def PLUS (*args):
    return '(?:' + CONCAT(*args) + ')+'

def SPLAT (*args):
    return '(?:' + CONCAT(*args) + ')*'

def NAME (name, arg):
    return '(?P<%s>%s)' % (name, arg)
