from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in customer_statement/__init__.py
from customer_statement import __version__ as version

setup(
	name="customer_statement",
	version=version,
	description="customer statement",
	author="Techseria",
	author_email="support@techseria.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
