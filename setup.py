#!/usr/bin/env python
"""
distutils/setuptools install script. See inline comments for packaging documentation.
"""
import os
import sys
import idigi_monitor_api

try:
    from setuptools import setup
    # hush pyflakes
    setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

packages = [
    'idigi_monitor_api'
]

requires = ['argparse']

setup(
    name='idigi_monitor_api',
    version=idigi_monitor_api.__version__,
    description='iDigi Monitor API Library for Python.',
    author='Digi International',
    author_email='support@digi.com',
    url='http://www.idigi.com',
    packages=packages,
    package_data={'': ['LICENSE'], 'idigi_monitor_api' : ['idigi.crt']},
    include_package_data=True,
    install_requires=requires,
    license=open("LICENSE").read(),
    classifiers=(
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.1',
    ),
)