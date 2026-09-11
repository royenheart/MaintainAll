from setuptools import setup

setup(
    name="cuactl",
    version="0.1.0",
    py_modules=["relay_server"],
    entry_points={
        "console_scripts": [
            "cuactl=relay_server:main",
        ],
    },
    install_requires=["httpx>=0.28.0"],
)
