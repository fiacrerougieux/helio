"""
Setup script for Helio CLI installation.

Install with: pip install -e .

This creates a 'helio' command that launches the agent from anywhere.
"""

from setuptools import setup, find_packages
from pathlib import Path
import sys
import os

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

def print_post_install_message():
    """Print helpful message after installation."""
    if sys.platform == "win32":
        python_version = f"Python{sys.version_info.major}{sys.version_info.minor}"
        appdata = os.environ.get('APPDATA', 'C:\\Users\\YOUR_USER\\AppData\\Roaming')
        scripts_dir = f"{appdata}\\Python\\{python_version}\\Scripts"

        print("\n" + "=" * 60)
        print("✅ Helio installed successfully!")
        print("=" * 60)
        print("\nTo run Helio, try:")
        print("  helio")
        print("\nIf 'helio' is not found, add Scripts to PATH:")
        print(f'  setx PATH "%PATH%;{scripts_dir}"')
        print("  (then restart terminal)")
        print("\nOr run directly:")
        print("  python -m agent.cli")
        print("  helio.bat  (from project directory)")
        print("\nFor detailed setup help, run:")
        print("  python setup_path.py")
        print("=" * 60 + "\n")
    else:
        print("\n✅ Helio installed! Run with: helio\n")

setup(
    name="helio",
    version="0.3.0",
    description="AI Companion for Solar PV Simulation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Fiacre Rougieux",
    author_email="fiacrerougieux@gmail.com",
    url="https://github.com/fiacrerougieux/sun-sleuth-dev",
    packages=find_packages(exclude=["tests*", "docs*"]),
    python_requires=">=3.11",
    install_requires=[
        "pvlib>=0.14.0,<0.15.0",
        "numpy>=1.24.0,<2.0.0",
        "pandas>=2.0.0,<3.0.0",
        "scipy>=1.10.0",
        "matplotlib>=3.7.0",
        "requests>=2.31.0",
        "pydantic>=2.0.0",
        "rich>=13.0.0",
        "click>=8.1.0",
        "keyring>=24.0.0",  # Secure credential storage
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
        "training": [
            # These are large packages, make them optional
            # "torch>=2.1.0",
            # "transformers>=4.36.0",
            # "datasets>=2.14.0",
            # "trl>=0.7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "helio=agent.multi_agent_cli:main",
            "helio-auth=agent.auth_cli:main",
            "sun=agent.multi_agent_cli:main",  # Keep as alias during transition
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    keywords="solar pv pvlib simulation ai llm agent",
)
