import setuptools

setuptools.setup(
    name="{{ cookiecutter.project_name }}",
    version="0.0.1",
    author="{{ cookiecutter.ptl }}",
    author_email="{{ cookiecutter.ptl }}@cinnamon.is",
    description="Project {{ cookiecutter.project_name }}",
    long_description="Project {{ cookiecutter.project_name }}",
    url="https://github.com/Cinnamon/maia",
    python_requires=">=3",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "maia@git+ssh://git@github.com/Cinnamon/maia.git",
    ],
)
