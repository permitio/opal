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

about = get_package_metadata()
version = about.get('__version__')
license = about.get('__license__')
if not version or not license:
    raise ValueError('could not find project metadata!')

setup(
    name='opal-common',
    version=version,
    author='Or Weis, Asaf Cohen',
    author_email="or@permit.io",
    description='OPAL is an administration layer for Open Policy Agent (OPA), detecting changes' + \
        ' to both policy and data and pushing live updates to your agents. opal-common contains' + \
        ' common code used by both opal-client and opal-server.',
    long_description_content_type='text/markdown',
    long_description=get_long_description(),
    url='https://github.com/permitio/opal',
    license=license,
    packages=find_packages(where=project_root, include=('opal_common*', )),
    classifiers=[
        'Operating System :: OS Independent',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: WSGI'
    ],
    python_requires='>=3.7',
    install_requires=get_requirements(),
)