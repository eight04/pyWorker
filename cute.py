#! python3

from xcute import cute, Exc

cute(
    pkg_name = 'worker',
    lint = 'pylint worker cute docs/conf.py setup test',
    test = ['lint', 'python test.py', 'readme_build'],
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
    readme_build = 
        'mkdir build & python setup.py --long-description > build/ld && '
        'rst2html --no-raw --exit-status=1 --verbose build/ld build/ld.html',
    readme_build_err = ['readme_show', Exc()],
    readme_show = 'start %temp%/ld.html',
    readme = 'readme_build',
    readme_post = 'readme_show',
    doc = 'sphinx-autobuild -B -z worker docs docs/build'
)
