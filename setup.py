import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='docker-cluster-controller',
    version='0.1.8',
    author='erik.de.wildt',
    author_email='erik.de.wildt@gmail.com',
    description="A simple Python class to orchestrate cluster nodes within a docker environment.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/erikdewildt/docker-cluster-controller",
    packages=find_packages(),
    license='GNU GENERAL PUBLIC LICENSE',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: System :: Clustering'
    ],
    install_requires=[
        'Jinja2==2.10',
        'python-etcd==0.4.5',
        'schedule==0.6.0',
        'raven==6.10.0',
    ],
)
