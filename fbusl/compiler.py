from fbusl.parser import Lexer, Parser
from typing import Literal
import sys
from enum import Enum, auto


class ShaderType:
    VERTEX = auto()
    FRAGMENT = auto()
    COMPUTE = auto()
    GEOMETRY = auto()


def compile(source):
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    parser.parse()

