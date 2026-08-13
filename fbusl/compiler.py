from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.optimizer import Optimizer
from fbusl.generator import Generator
from fbusl.injector import Injector
from typing import Literal
import sys
from enum import Enum, auto
from fbusl import ShaderType, FBUSLError
from FreeBodyEngine.core.files.resource import FileResource


def compile(source, shader_type: ShaderType, generator_class: type[Generator], injector: Injector = Injector()):
    injector.initialize(shader_type)
    if not isinstance(source, str):
        path = source.file_path
        source = source.read()
    else:
        path = None
    lexer = Lexer(injector.source_inject(source), path)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    tree = injector.ast_inject(parser.parse())
    
    semantics = SemanticAnalyser(tree, shader_type, injector.get_builtins())
    semantics.analyse()

    optimizer = Optimizer(tree)
    tree = optimizer.optimize()

    generator = generator_class(tree)
    output = generator.generate()
    print(output)
    return output 