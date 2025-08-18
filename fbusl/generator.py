from fbusl.ast_nodes import *
from fbusl.semantic import SemanticAnalyser

class Generator:
    """
    The code generator for FBUSL ASTs.
    """
    def __init__(self, tree: Tree, analyser: SemanticAnalyser, buffer_index: int):
        self.tree = tree
        self.analyser = analyser
        self.buffer_index = buffer_index

    def generate(self) -> str:
        pass