import os
from types import SimpleNamespace

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.abspath(os.path.join(here, '../../'))
project_root = os.path.normpath(os.path.join(here, os.pardir))


def get_package_metadata():
    metadata = {}
    with open(os.path.join(here, '../__packaging__.py')) as f:
        exec(f.read(), metadata)
    return SimpleNamespace(**metadata)


def get_relative_path(path):
    return os.path.join(here, os.path.pardir, path)


def get_long_description():
    readme_path = os.path.join(root, "README.md")

    with open(readme_path, "r", encoding="utf-8") as fh:
        return fh.read()


about = get_package_metadata()

setup(
    name='opal-common',
    version=about.__version__,
    author='Or Weis, Asaf Cohen',
    author_email="or@permit.io",
    description='OPAL is an administration layer for Open Policy Agent (OPA), detecting changes' + \
        ' to both policy and data and pushing live updates to your agents. opal-common contains' + \
        ' common code used by both opal-client and opal-server.',
    long_description_content_type='text/markdown',
    long_description=get_long_description(),
    url='https://github.com/permitio/opal',
    license=about.__license__,
    packages=['opal_common'],
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
    install_requires=[
        'typer',
        'aiohttp',
        'fastapi==0.65.2',
        'fastapi_websocket_pubsub>=0.2.0',
        'fastapi_websocket_rpc>=0.1.21',
        'GitPython',
        'gunicorn',
        'loguru==0.6.0',
        'pydantic[email]',
        'pyjwt[crypto]==2.1.0',
        'python-decouple',
        'tenacity',
        'typing-extensions',
        'uvicorn[standard]',
        'websockets==9.1',
        'ddtrace'
    ],
)