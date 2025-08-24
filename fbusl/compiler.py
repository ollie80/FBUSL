from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.optimizer import Optimizer
from fbusl.generator import Generator
from typing import Literal
import sys
from enum import Enum, auto
from fbusl import ShaderType, FBUSLError


def compile(source, shader_type: ShaderType):
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    tree = parser.parse()
    print(tree)
    sys.exit()


    semantics = SemanticAnalyser(tree, shader_type)
    semantics.analyse()

    optimizer = Optimizer(tree)
    tree = optimizer.optimize()

    generator = Generator(tree)
    return generator.generate()
