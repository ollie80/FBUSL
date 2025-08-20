from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from typing import Literal
import sys
from enum import Enum, auto
from fbusl import ShaderType, FBUSLError


def compile(source, shader_type: ShaderType):
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    tree = parser.parse()
    
    semantics = SemanticAnalyser(tree, shader_type)
    semantics.analyse()

    

if __name__ == "__main__":
    source = open('test.fbvert').read()
    compile(source, ShaderType.VERTEX)
