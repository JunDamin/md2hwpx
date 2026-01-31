from pathlib import Path

from setuptools import setup, find_packages


def read_version():
    version_file = Path(__file__).parent / "md2hwpx" / "__init__.py"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("Unable to find __version__ in md2hwpx/__init__.py")


def read_readme():
    return Path(__file__).parent.joinpath("README.md").read_text(encoding="utf-8")

setup(
    name="md2hwpx",
    version=read_version(),
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'md2hwpx': ['blank.hwpx'],
    },
    install_requires=[
        "marko>=2.0.0",
        "python-frontmatter>=1.0.0",
        "Pillow",
    ],
    entry_points={
        'console_scripts': [
            'md2hwpx=md2hwpx.cli:main',
        ],
    },
    author="md2hwpx Contributors",
    url="https://github.com/jundamin/md2hwpx",
    project_urls={
        "Source": "https://github.com/jundamin/md2hwpx",
        "Tracker": "https://github.com/jundamin/md2hwpx/issues",
        "Fork of": "https://github.com/msjang/pypandoc-hwpx",
    },
    description="Convert Markdown to HWPX (Korean Hancom Office format)",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
)
