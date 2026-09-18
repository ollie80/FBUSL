from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.optimizer import Optimizer
from fbusl.generator import Generator
from fbusl.injector import Injector
from typing import Literal
import sys
from enum import Enum, auto
from fbusl import ShaderType, FBUSLError


def compile(source, shader_type: ShaderType, generator_class: type[Generator], injector: Injector = Injector()):
    """Compiles FBUSL source into a target-language string via `generator_class`.

    `source` may be a plain string, or any object duck-typing a `FileResource`
    (`.data.path` + `.read()`) - this module intentionally does not import or
    depend on FreeBodyEngine's concrete `FileResource` type, since `fbusl` is a
    standalone package that FreeBodyEngine depends on, not the other way around.
    """
    injector.initialize(shader_type)
    if not isinstance(source, str):
        path = source.data.path
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


    generator = generator_class(tree, shader_type)
    output = generator.generate()
    return output
