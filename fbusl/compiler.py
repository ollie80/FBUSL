from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.optimizer import Optimizer
from fbusl.generator import Generator
from fbusl.injector import Injector
from typing import Literal
import sys
from enum import Enum, auto
from fbusl import ShaderType, FBUSLError


def compile(source, shader_type: ShaderType, generator_class: type[Generator], injector_class: type[Injector] = Injector):
    injector = injector_class(shader_type)
    
    lexer = Lexer(injector.source_inject(source))
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    tree = injector.ast_inject(parser.parse())
    
    semantics = SemanticAnalyser(tree, shader_type, injector.get_builtins())
    semantics.analyse()

    optimizer = Optimizer(tree)
    tree = optimizer.optimize()


    generator = generator_class(tree)
    return generator.generate()
