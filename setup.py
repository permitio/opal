from setuptools import setup, find_packages

def get_requirements(env=""):
    if env:
        env = "-{}".format(env)
    with open("requirements{}.txt".format(env)) as fp:
        return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]

setup(
    name='acalla',
    version='0.1.0',
    packages=find_packages(),
    python_requires='>=3.8',
    install_requires=get_requirements(),
    # dev_requires=get_requirements("dev"),
)