#! python3

from xcute import cute, LiveReload

cute(
    pkg_name = 'worker',
    lint = 'pylint worker cute docs/conf.py setup test',
    unit = "coverage run --source worker -m unittest",
    test = ['lint', 'unit', 'coverage report', 'readme_build'],
    bump_pre = 'test',
    bump_post = ['dist', 'release', 'publish', 'install'],
    dist = ['rm -r build dist & python setup.py sdist bdist_wheel'],
    release = [
        'git add .',
        'git commit -m "Release v{version}"',
        'git tag -a v{version} -m "Release v{version}"'
        ],
    publish = [
        'twine upload dist/*{version}*',
        'git push --follow-tags'
        ],
    install = 'pip install -e .',
    install_err = 'elevate -c -w pip install -e .',
    readme_build = [
        'python setup.py --long-description | x-pipe build/readme/index.rst',
        'rst2html5.py --no-raw --exit-status=1 --verbose '
        'build/readme/index.rst build/readme/index.html'
        ],
    readme_pre = "readme_build",
    readme = LiveReload("README.rst", "readme_build", "build/readme"),
    doc = 'sphinx-autobuild -B -z worker docs docs/build',
    coverage_pre = ["unit", "coverage html"],
    coverage = LiveReload(["worker", "test.py"], "coverage_pre", "htmlcov")
    )
