============
Installation
============

Supported Platforms
===================
Shrapnel currently works on FreeBSD, Linux, and Mac OS X with x86 32- or 64-bit platforms. 
It supports Python 2.7 (TODO: and 2.6?).

Prerequisites
=============
pip
---
To make installation easy, you can use `pip <http://www.pip-installer.org/>`_.
This is a tool which will fetch Python packages from `PyPi
<http://pypi.python.org/>`_ and install them.

Visit http://www.pip-installer.org/en/latest/installing.html for information
on how to install pip if you don't already have it installed.

Cython
------
You need version 0.12.1 or newer of `Cython <http://cython.org/>`_.  If you
already have Cython installed, you can check your current version by running
``cython -V``.

To install Cython, run:

	pip install cython

Distribute
----------
You need version 0.6.16 or newer of `distribute <http://pypi.python.org/pypi/distribute>`_.
Distribute is a build and packaging tool for Python (a replacement for setuptools).

To install distribute, run:

	pip install distribute

Shrapnel
--------
Finally, you can install Shrapnel, run:

	pip install shrapnel

Alternatively you can download it from https://github.com/ironport/shrapnel
and do the usual ``python setup.py install`` procedure.
