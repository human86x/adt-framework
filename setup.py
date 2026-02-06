from setuptools import setup, find_packages

setup(
    name="adt-framework",
    version="0.1.0",
    description="Advanced Digital Transformation -- Governance-Native AI Agent Management",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Paul Sheridan",
    license="AGPL-3.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "flask>=3.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-cov"],
    },
    entry_points={
        "console_scripts": [
            "adt=adt_core.cli:main",
        ],
    },
)
