from fbusl.node import *
from fbusl import ShaderType

class Injector:
    def __init__(self, shader_type: ShaderType):
        self.shader_type = shader_type
    
    def get_builtins(self) -> dict:
        return {}

    def ast_inject(self, tree: list[ASTNode]):
        return tree

    def source_inject(self, source: str) -> str:
        return source