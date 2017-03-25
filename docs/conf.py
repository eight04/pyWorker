#! python3

import os.path
import sys

sys.path.insert(0, os.path.realpath(__file__ + "/../.."))
extensions = ["sphinx.ext.autodoc"]
master_doc = "index"
autodoc_member_order = "bysource"

def process_signature(app, what, name, obj, options, signature, 
		return_annotation):
	if what == "class":
		return (None, return_annotation)
		
def setup(app):
	app.connect("autodoc-process-signature", process_signature)
