from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in waafipay_integration/__init__.py
from waafipay_integration import __version__ as version

setup(
	name="waafipay_integration",
	version=version,
	description="Frappe app for Waafiipay Integration",
	author="Miguel Higuera",
	author_email="migueladolfohiguera@hotmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
