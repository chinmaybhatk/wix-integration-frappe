from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in wix_integration/__init__.py
from wix_integration import __version__ as version

setup(
	name="wix_integration",
	version=version,
	description="Wix ecommerce integration for unified CRM, inventory management, and order processing",
	author="KokoFresh",
	author_email="admin@kokofresh.in",
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