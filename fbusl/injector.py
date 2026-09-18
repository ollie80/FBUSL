from fbusl.node import *
from fbusl import ShaderType

class Injector:
    def initialize(self, shader_type: ShaderType):
        self.shader_type = shader_type

    def get_builtins(self) -> dict:
        return {}

    def ast_inject(self, tree: list[ASTNode]):
        return tree

    def source_inject(self, source: str) -> str:
        return source

    def replace_expr(self, node: ASTNode, matcher, replacer) -> ASTNode:
        """Bottom-up substitution over the known FBUSL expression node shapes.

        `matcher(node) -> bool` decides whether a node should be replaced;
        `replacer(node) -> ASTNode` produces its replacement. Returns the
        (possibly new) node. ASTNode has no parent pointers, so this can only
        mutate through the expression-node kinds it explicitly knows about -
        it does not attempt to rewrite statement-level structure.
        """
        if node is None:
            return None

        if isinstance(node, BinOp):
            node.left = self.replace_expr(node.left, matcher, replacer)
            node.right = self.replace_expr(node.right, matcher, replacer)
        elif isinstance(node, UnaryOp):
            node.operand = self.replace_expr(node.operand, matcher, replacer)
        elif isinstance(node, InlineIf):
            node.then_expr = self.replace_expr(node.then_expr, matcher, replacer)
            node.condition = self.replace_expr(node.condition, matcher, replacer)
            node.else_expr = self.replace_expr(node.else_expr, matcher, replacer)
        elif isinstance(node, FuncCall):
            node.args = [self.replace_expr(a, matcher, replacer) for a in node.args]
        elif isinstance(node, MemberAccess):
            node.base = self.replace_expr(node.base, matcher, replacer)
        elif isinstance(node, ArrayAccess):
            node.base = self.replace_expr(node.base, matcher, replacer)
            node.index = self.replace_expr(node.index, matcher, replacer)
        elif isinstance(node, Setter):
            node.value = self.replace_expr(node.value, matcher, replacer)
        elif isinstance(node, VarDecl) and node.value is not None:
            node.value = self.replace_expr(node.value, matcher, replacer)

        return replacer(node) if matcher(node) else node

    def walk_body(self, body: list[ASTNode]):
        """Yields every statement in `body`, recursing into control-flow bodies
        (if/elif/else chains, and while-loop bodies once that node exists) so
        callers can find/rewrite statements nested inside them."""
        for stmt in body:
            yield stmt
            if isinstance(stmt, IfStatement):
                yield from self.walk_body(stmt.body)
                if stmt.next_statement is not None:
                    yield from self.walk_body([stmt.next_statement])
            elif isinstance(stmt, WhileStatement):
                yield from self.walk_body(stmt.body)