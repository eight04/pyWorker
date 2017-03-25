#! python3

import os.path
import sys

sys.path.insert(0, os.path.realpath(__file__ + "/../.."))
extensions = ["sphinx.ext.intersphinx", "sphinx.ext.autodoc"]
master_doc = "index"
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}
