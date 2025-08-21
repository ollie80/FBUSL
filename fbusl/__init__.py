"""
The FreeBody Universal Shader Language is a Transpiled Shader Language.
It includes features present in many shader languages so it can
be easily compiled into them.
"""

import sys


class Position:
    def __init__(
        self,
        line: int = 0,
        file: str = None,
        column: int = 0,
        start: int = 0,
        end: int = 0,
    ):
        self.line = line
        self.file = file
        self.column = column
        self.start = start
        self.end = end

    def __repr__(self):
        return f"{self.line}"


class FBUSLError:
    def __init__(self, msg, position: Position = Position()):
        self.msg = msg
        self.position = position


_FBUSL_errors: list[FBUSLError] = []


def get_errors() -> list[FBUSLError]:
    """Gets all errors and then resets the errors"""
    global _FBUSL_errors
    val = _FBUSL_errors.copy()
    reset_errors()
    return val


def _add_error(err: FBUSLError):
    global _FBUSL_errors
    _FBUSL_errors.append(err)


def reset_errors():
    global _FBUSL_errors
    _FBUSL_errors = []


def fbusl_error(msg, position: Position = Position()):
    f = position.file
    if position.file == None:
        f = "Unkown File"

    print(f'\033[91mFBUSL ERROR: {msg} in file "{f}", line {position.line}.\033[0m')
    _add_error(FBUSLError(msg, position))


class ShaderType:
    VERTEX = "vertex"
    FRAGMENT = "fragment"
    COMPUTE = "compute"
    GEOMETRY = "geometry"

from fbusl import semantic
from fbusl import optimizer
from fbusl import parser
from fbusl import generator
from fbusl.compiler import compile


__all__ = ["fbusl_error", "ShaderType", "Position", "parser", "generator", "compile", "optimizer", "semantic"]
