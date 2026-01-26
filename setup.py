from setuptools import setup, find_packages

setup(
    name="md2hwpx",
    version="0.2.0",
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
    url="https://github.com/msjang/md2hwpx",
    project_urls={
        "Source": "https://github.com/msjang/md2hwpx",
        "Tracker": "https://github.com/msjang/md2hwpx/issues",
    },
    description="Convert Markdown to HWPX (Korean Hancom Office format)",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
)
