import os.path
import sys
sys.path.insert(0, os.path.realpath(__file__ + "/../.."))
extensions = ["sphinx.ext.autodoc"]
master_doc = "index"

def skip(app, what, name, obj, skip, options):
    if name == "__init__" and obj.__doc__:
        return False
    return skip

def setup(app):
    app.connect("autodoc-skip-member", skip)
	