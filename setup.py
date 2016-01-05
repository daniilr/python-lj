from setuptools import setup, find_packages

setup(
    name='lj',
    packages=['lj'],
    version='0.2',
    description='Python realization of LiveJournal (LJ) API.'
                'Checkout https://github.com/daniilr/python-lj for more info',
    long_description=open('DESCRIPTION.rst').read(),
    licence='The BSD 3-Clause License',
    author='Original developer: David Lynch; Curent maintainer: Daniil Ryzhkov ',
    author_email='i@daniil-r.ru',
    url='https://github.com/daniilr/python-lj',
    download_url='https://github.com/daniilr/python-lj/tarball/0.2',
    keywords=['livejournal', 'blog', 'writing'],
    classifiers=[],
    platforms='osx, posix, linux, windows',
)
