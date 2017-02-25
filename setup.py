#! python3

import re
from os import path

from setuptools import setup, find_packages

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
def read(file):
    with open(path.join(here, file), encoding='utf-8') as f:
        content = f.read()
    return content

def find_version(file):
    return re.search(r"__version__ = (\S*)", read(file)).group(1).strip("\"'")

setup(
    name="pythreadworker",
    version=find_version("worker/__init__.py"),
    description='A threading library written in python',
    long_description=read("README.rst"),
    url='https://github.com/eight04/pyWorker',
    author='eight',
    author_email='eight04@gmail.com',
    license='MIT',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5'
    ],
    keywords='thread threading worker',
    packages=find_packages()
)
