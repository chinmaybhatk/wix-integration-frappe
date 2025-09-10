from setuptools import setup, find_packages
import os

# Read requirements
install_requires = []
if os.path.exists("requirements.txt"):
    with open("requirements.txt") as f:
        install_requires = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]

# Read version
version = "1.0.0"
try:
    from wix_integration import __version__ as version
except ImportError:
    pass

setup(
    name="wix_integration",
    version=version,
    description="Wix ecommerce integration for unified CRM, inventory management, and order processing",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="KokoFresh",
    author_email="admin@kokofresh.in",
    url="https://github.com/chinmaybhatk/wix-integration-frappe",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Frappe",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Office/Business :: Financial :: Accounting",
    ],
)