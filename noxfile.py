"""Nox sessions."""
import contextlib
from pathlib import Path
import shutil
import tempfile
from typing import cast
from typing import Iterator

import nox
from nox.sessions import Session


package = "vidgen"
python_versions = ["3.8", "3.7"]
nox.options.sessions = "safety", "mypy", "pytype", "tests"
locations = "src", "tests", "noxfile.py", "docs/conf.py"


class Poetry:
    """Helper class for invoking Poetry inside a Nox session.

    Attributes:
        session: The Session object.
    """

    def __init__(self, session: Session) -> None:
        """Constructor."""
        self.session = session

    @contextlib.contextmanager
    def export(self, *args: str) -> Iterator[Path]:
        """Export the lock file to requirements format.

        Args:
            args: Command-line arguments for ``poetry export``.

        Yields:
            The path to the requirements file.
        """
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / "requirements.txt"
            self.session.run(
                "poetry",
                "export",
                *args,
                "--format=requirements.txt",
                f"--output={requirements}",
                external=True,
            )
            yield requirements

    def version(self) -> str:
        """Retrieve the package version.

        Returns:
            The package version.
        """
        output = self.session.run(
            "poetry", "version", external=True, silent=True, stderr=None
        )
        return cast(str, output).split()[1]

    def build(self, *args: str) -> None:
        """Build the package.

        Args:
            args: Command-line arguments for ``poetry build``.
        """
        self.session.run("poetry", "build", *args, external=True)


def install_package(session: Session) -> None:
    """Build and install the package.

    Build a wheel from the package, and install it into the virtual environment
    of the specified Nox session.
    The package requirements are installed using the versions specified in
    Poetry's lock file.

    Args:
        session: The Session object.
    """
    poetry = Poetry(session)

    with poetry.export() as requirements:
        session.install(f"--requirement={requirements}")

    poetry.build("--format=wheel")

    version = poetry.version()
    session.install(
        "--no-deps", "--force-reinstall", f"dist/{package}-{version}-py3-none-any.whl"
    )


def install(session: Session, *args: str) -> None:
    """Install development dependencies into the session's virtual environment.

    This function is a wrapper for nox.sessions.Session.install.
    The packages must be managed as development dependencies in Poetry.

    Args:
        session: The Session object.
        args: Command-line arguments for ``pip install``.
    """
    poetry = Poetry(session)
    with poetry.export("--dev") as requirements:
        session.install(f"--constraint={requirements}", *args)


@nox.session(python="3.8")
def safety(session: Session) -> None:
    """Scan dependencies for insecure packages."""
    poetry = Poetry(session)
    with poetry.export("--dev", "--without-hashes") as requirements:
        install(session, "safety")
        session.run("safety", "check", f"--file={requirements}", "--bare")


@nox.session(python="3.8")
def black(session: Session) -> None:
    """Run black code formatter."""
    args = session.posargs or locations
    install(session, "black")
    session.run("black", *args)


@nox.session(python=python_versions)
def lint(session: Session) -> None:
    """Lint using flake8."""
    args = session.posargs or locations
    install(
        session,
        "flake8",
        "flake8-annotations",
        "flake8-bandit",
        "flake8-black",
        "flake8-bugbear",
        "flake8-docstrings",
        "flake8-import-order",
        "darglint",
    )
    session.run("flake8", *args)


@nox.session(python=python_versions)
def mypy(session: Session) -> None:
    """Type-check using mypy."""
    args = session.posargs or locations
    install_package(session)
    install(session, "mypy")
    session.run("mypy", *args)


@nox.session(python=python_versions)
def pytype(session: Session) -> None:
    """Type-check using pytype."""
    args = session.posargs or ["--disable=import-error", *locations]
    # install(session, "pytype")
    # Weird error means can't use poetry for pytype
    session.install("pytype==2020.6.1")
    session.run("pytype", *args)


@nox.session(python=python_versions)
def tests(session: Session) -> None:
    """Run the test suite."""
    install_package(session)
    install(session, "coverage[toml]", "pytest", "pytest-mock")
    try:
        session.run("coverage", "run", "--parallel", "-m", "pytest", *session.posargs)
    finally:
        session.notify("coverage")


@nox.session
def coverage(session: Session) -> None:
    """Produce the coverage report."""
    args = session.posargs or ["report"]
    install(session, "coverage[toml]")
    if not session.posargs and any(Path().glob(".coverage.*")):
        session.run("coverage", "combine")
    session.run("coverage", *args)


@nox.session(python="3.8")
def docs(session: Session) -> None:
    """Build the documentation."""
    args = session.posargs or ["docs", "docs/_build"]

    if session.interactive and not session.posargs:
        args.insert(0, "--open-browser")

    builddir = Path("docs", "_build")
    if builddir.exists():
        shutil.rmtree(builddir)

    install_package(session)
    install(session, "sphinx", "sphinx-autodoc-typehints", "sphinx-autobuild")

    if session.interactive:
        session.run("sphinx-autobuild", *args)
    else:
        session.run("sphinx-build", *args)
