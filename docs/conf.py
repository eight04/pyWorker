#! python3

# import os.path
# import sys
from subprocess import run

from worker import __version__

project = "pyThreadWorker"
author = "eight04 (https://github/eight04)"

r = run("git tag --points-at HEAD", capture_output=True, encoding="utf8", check=True)
is_tagged = r.stdout.strip()
if is_tagged:
    version = __version__
else:
    r = run("git rev-parse HEAD", capture_output=True, encoding="utf8", check=True)
    version = f"{__version__}+ ({r.stdout.strip()[:6]})"
release = version

add_module_names = False
extensions = ["sphinx.ext.intersphinx", "sphinx.ext.autodoc"]
master_doc = "index"
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}
autoclass_content = 'both'
