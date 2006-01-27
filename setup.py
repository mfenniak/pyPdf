#!/usr/bin/env python

from distutils.core import setup

long_description = """
A Pure-Python library built as a PDF toolkit.  At present, there is only one
actual tool in the toolkit - the ability to grab pages from PDFs and output
them into a new PDF.  Like a hammer, this tool is useful for two operations:
splitting and merging.  You can extract individual pages from a PDF file,
or selectively merge pages from multiple PDF files.

By being Pure-Python, it should run on any Python platform without any
dependencies on external libraries.  It can also work entirely on StringIO
objects rather than file streams, allowing for PDF manipulation in memory.
It is therefore a useful tool for websites that manage or manipulate PDFs.
"""

setup(
        name="pyPdf",
        version="1.4",
        description="PDF toolkit",
        long_description=long_description,
        author="Mathieu Fenniak",
        author_email="mfenniak@pobox.com",
        url="http://pybrary.net/pyPdf/",
        download_url="http://pybrary.net/pyPdf/pyPdf-1.4.tar.gz",
        classifiers = [
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: BSD License",
            "Programming Language :: Python",
            "Operating System :: OS Independent",
            "Topic :: Software Development :: Libraries :: Python Modules",
            ],
        packages=["pyPdf"],
    )

