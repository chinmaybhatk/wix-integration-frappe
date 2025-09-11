from setuptools import setup, find_packages
import os

# Read requirements - only external dependencies
install_requires = [
    "requests>=2.28.0",
    "python-dateutil>=2.8.0", 
    "cryptography>=3.4.8"
]

# Version
version = "1.0.0"

setup(
    name="wix_integration",
    version=version,
    description="Wix ecommerce integration for unified CRM, inventory management, and order processing (Frappe v14/v15)",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Chinmay Bhatk",
    author_email="chinmaybhatk@gmail.com",
    url="https://github.com/chinmaybhatk/wix-integration-frappe",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.8",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment", 
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)