from fbusl.node import ASTNode

class Generator:
    """
    Generates shader code from a FBUSL AST.
    """
    def __init__(self, tree: ASTNode):
        self.tree = tree

    def generate(self) -> str:
        pass