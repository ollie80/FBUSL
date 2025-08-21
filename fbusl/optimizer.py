from fbusl.node import *

class Optimizer:
    def __init__(self, tree: list[ASTNode]):
        self.tree = tree
        
    def optimize(self):
        return self.tree