from fbusl.node import ASTNode

class Generator:
    def __init__(self, tree: ASTNode):
        self.tree = tree

    def generate(self) -> str:
        return ""