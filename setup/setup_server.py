import os
import sys

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.normpath(os.path.join(here, os.pardir))

def get_package_metadata():
    package_metadata = {}
    with open(os.path.join(here, '__version__.py')) as f:
        exec(f.read(), package_metadata)
    return package_metadata

def get_relative_path(path):
    return os.path.join(here, os.path.pardir, path)

def get_requirements(env=""):
    if env:
        env = "-{}".format(env)
    requirements_path = get_relative_path("requirements{}.txt".format(env))
    with open(requirements_path) as fp:
        return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]

def get_long_description():
    readme_path = get_relative_path("README.md")

    with open(readme_path, "r", encoding="utf-8") as fh:
        return fh.read()

package = get_package_metadata()
version = package.get('__version__')
if not version:
    raise ValueError('could not find project version!')

requirements = get_requirements()
requirements.append('opal-common=={}'.format(version))

setup(
    name='opal-server',
    version=version,
    author='Or Weis, Asaf Cohen',
    author_email="or@authorizon.com",
    description='OPAL is an administration layer for Open Policy Agent (OPA), detecting changes' + \
        ' to both policy and data and pushing live updates to your agents. The opal-server creates' + \
        ' a pub/sub channel clients can subscribe to (i.e: acts as coordinator). The server also' + \
        ' tracks a git repository (via webhook) for updates to policy (or static data) and accepts' + \
        ' continuous data update notifications via REST api, which are then pushed to clients.',
    long_description_content_type='text/markdown',
    long_description=get_long_description(),
    url='https://github.com/authorizon/opal',
    packages=find_packages(where=project_root, include=('opal_server*', )),
    classifiers=[
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: WSGI'
    ],
    python_requires='>=3.7',
    install_requires=requirements,
)