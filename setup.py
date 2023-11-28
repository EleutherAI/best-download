import setuptools
import os
from io import open as io_open

src_dir = os.path.abspath(os.path.dirname(__file__))

with open("README.md", "r") as fh:
    long_description = fh.read()

# Build requirements
extras_require = {}
requirements_dev = os.path.join(src_dir, 'requirements-dev.txt')
with io_open(requirements_dev, mode='r') as fd:
    extras_require['dev'] = [i.strip().split('#', 1)[0].strip()
                             for i in fd.read().strip().split('\n')]


install_requires = ["requests", "rehash", "tqdm"]

setuptools.setup(
    name="best-download",
    version="1.0.0",
    author="researcher2",
    author_email="contact@eleuther.ai",
    description="URL downloader supporting checkpointing and continuous checksumming.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EleutherAI/best-download",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],

    python_requires='>=3.6',
    extras_require=extras_require,
    install_requires=install_requires,
    packages=['best_download'],
    package_data={'best_download': ['LICENCE', 'examples/*.py','requirements-dev.txt']},
)
