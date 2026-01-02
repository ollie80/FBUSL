from fbusl.node import *
from fbusl.builtins import TYPES, BUILTINS
from fbusl import fbusl_error, Position
from fbusl import ShaderType

class Scope:
    def __init__(self, parent: "Scope" = None):
        self.parent = parent
        self.variables = {}

    def get_all_vars(self):
        p_vars = {}
        if self.parent:
            self.parent.get_all_vars()
        return self.variables.copy() | p_vars

    def declare(
        self, name: str, var_type, position: Position, mutable=True, initialized=True
    ):
        if name in self.variables:
            fbusl_error(f"Variable '{name}' already declared in this scope", position)
        self.variables[name] = {
            "type": var_type,
            "mutable": mutable,
            "initialized": initialized,
        }

    def initialize_variable(self, name):
        if name not in self.variables:
            fbusl_error(f"Variable '{name}' is not delcared in this scope.")
        self.variables[name]["initialized"] = True

    def exists(self, name) -> bool:
        if name in self.variables:
            return True
        elif self.parent:
            return self.parent.exists(name)
        else:
            return False

    def lookup(self, name: str, pos: Position):
        if name in self.variables:
            return self.variables[name]
        elif self.parent:
            return self.parent.lookup(name, pos)
        else:
            fbusl_error(f"Variable '{name}' not defiened in current scope.", pos)

class SemanticAnalyser:
    def __init__(self, tree: list[ASTNode], shader_type: ShaderType, extra_builtins = {}):
        self.tree = tree
        self.shader_type = shader_type
        self.global_scope = Scope()
        self.types = TYPES.copy()

        self.current_scope = self.global_scope
        self.functions = {}

        self.define_builtins(extra_builtins)

    def define_builtins(self, extra):
        builtins: dict = BUILTINS.get("all") | BUILTINS.get(self.shader_type, {}) | extra

        for builtin_name in builtins:
            builtin_data = builtins[builtin_name]

            kind = builtin_data.get("kind")
            if kind == "function":
                self.define_function(
                    builtin_name,
                    builtin_data.get("return"),
                    builtin_data.get("params"),
                    builtin_data.get("overloads"),
                    Position(),
                )

            if kind == "output":
                self.current_scope.declare(
                    builtin_name, builtin_data.get("type"), Position
                )

    def define_function(
        self,
        name: str,
        return_type,
        params: dict[str, dict],
        overloads=None,
        pos: Position = Position(),
    ):
        if name in self.functions:
            fbusl_error(f"Function '{name}' already defined", pos)
        self.functions[name] = {
            "type": return_type,
            "params": params,
            "overloads": overloads,
        }

    def create_type(self, name: str, data: dict, pos: Position):
        if name in self.types:
            fbusl_error(f'Type "{name}" already exists.', pos)
        self.types[name] = data

    def analyse(self):
        for node in self.tree:
            self.analyse_node(node)
        for node in self.tree:
            self.set_node_types(node)

    def get_type_name(self, base_type: str | dict | None):
        if base_type is None:
            return "void"
        if isinstance(base_type, dict):
            return base_type.get("name", "unknown")
        return base_type

    def get_binop_type(
        self, op: str, left: ASTNode, right: ASTNode, pos: Position
    ) -> str:
        left_type = self.get_node_type(left)
        right_type = self.get_node_type(right)
        left_def = self.types.get(left_type)

        if not left_def:
            fbusl_error(f"Unknown type '{left_type}' in binary operation", pos)
            
        operations = left_def.get("operations", {})
        rules = operations.get(op)
        
        if not rules:
            fbusl_error(
                f"Type '{left_type}' does not support operator '{op}'",
                pos,
           )

        result_type = rules.get(right_type)

        if not result_type:
            fbusl_error(
                f"Operator '{op}' not supported between '{left_type}' and '{right_type}'",
                pos,
            )        
    
        return result_type

    def set_node_types(self, node: ASTNode) -> str:
        if isinstance(node, VarDecl):
            if node.value:
                self.set_node_types(node.value)
            node.type = self.get_node_type(node)

        elif isinstance(node, Identifier):
            node.type = self.get_node_type(node)

        elif isinstance(node, Literal):
            node.type = self.get_node_type(node)

        elif isinstance(node, Setter):
            self.set_node_types(node.node)
            self.set_node_types(node.value)
            node.type = self.get_node_type(node)

        elif isinstance(node, BinOp):
            self.set_node_types(node.left)
            self.set_node_types(node.right)
            node.type = self.get_node_type(node)

        elif isinstance(node, UnaryOp):
            self.set_node_types(node.operand)
            node.type = self.get_node_type(node)

        elif isinstance(node, InlineIf):
            self.set_node_types(node.condition)
            self.set_node_types(node.then_expr)
            self.set_node_types(node.else_expr)
            node.type = self.get_node_type(node)

        elif isinstance(node, MemberAccess):
            self.set_node_types(node.base)
            node.type = self.get_node_type(node)

        elif isinstance(node, FuncCall):
            for arg in node.args:
                self.set_node_types(arg)
            node.type = self.get_node_type(node)

        elif isinstance(node, StructDef):
            for field in node.fields:
                self.set_node_types(field)
            node.type = self.get_node_type(node)

        elif isinstance(node, FunctionDef):
            self.enter_scope()

            for param in node.params:
            
                self.set_node_types(param)
            
            for stmt in node.body:
            
                self.set_node_types(stmt)
            
            self.exit_scope()
            
            node.type = self.get_node_type(node)

        elif isinstance(node, Output):
            
            node.type = self.get_node_type(node)

        elif isinstance(node, Input):
            
            node.type = self.get_node_type(node)

        elif isinstance(node, Uniform):
            
            node.type = self.get_node_type(node)

        elif hasattr(node, "children"):
            
            for child in node.children:
            
                self.set_node_types(child)
            
            node.type = self.get_node_type(node)

        else:
        
            node.type = self.get_node_type(node.child)

        return node.type

    def get_node_type(self, node: ASTNode) -> str:
        
        if isinstance(node, VarDecl):
        
            return self.get_type_name(node.type)

        elif isinstance(node, Identifier):
        
            var = self.current_scope.lookup(node.value, node.pos)
            
            if var:
        
                return self.get_type_name(var["type"])

        elif isinstance(node, Literal):
        
            return self.get_type_name(node.type)

        elif isinstance(node, Setter):
        
            return self.get_node_type(node.value)

        elif isinstance(node, BinOp):
        
            return self.get_binop_type(node.op, node.left, node.right, node.pos)

        elif isinstance(node, UnaryOp):
        
            return self.get_node_type(node.operand)

        elif isinstance(node, InlineIf):
        
            return self.get_node_type(node.then_expr)

        elif isinstance(node, MemberAccess):
        
            base_type = self.get_type_name(self.get_node_type(node.base))

            struct_def = self.types.get(base_type)
        
            if struct_def:
        
                field_type = struct_def.get("fields", {}).get(node.member)
        
                if field_type is None:
        
                    fbusl_error(
        
                        f"Struct '{base_type}' has no member '{node.member}'",
        
                        node.pos,
        
                    )
        
                return self.get_type_name(field_type)

            fbusl_error(
        
                f"Cannot access member '{node.member}' on type '{base_type}'",
        
                node.pos,
        
            )

        elif isinstance(node, FuncCall):
        
            fn = self.functions.get(node.name)
            
            if not fn:
            
                fbusl_error(f"Function '{node.name}' not defined", node.pos)
            
                return
            
            return self.get_type_name(fn["type"])

        elif isinstance(node, StructDef):
        
            return node.name

        elif isinstance(node, ArrayAccess):
        
            return self.get_node_type(node.base) 

        elif hasattr(node, "type"):
        
            return self.get_type_name(node.type)

        return "unknown"

    def type_match(self, t1: str, t2: str):
        
        return t1 == t2

    def analyse_node(self, node: ASTNode):
        
        if isinstance(node, Output):
        
            self.analyse_output(node)

        elif isinstance(node, Input):
        
            self.analyse_input(node)

        elif isinstance(node, Uniform):
        
            self.analyse_uniform(node)

        elif isinstance(node, VarDecl):
        
            self.analyse_var_decl(node)

        elif isinstance(node, StructDef):
        
            self.analyse_struct_def(node)

        elif isinstance(node, Setter):
        
            self.analyse_setter(node)

        elif isinstance(node, FunctionDef):
        
            self.analyse_function_def(node)

        elif isinstance(node, FuncCall):
        
            self.analyse_function_call(node)

        for child in getattr(node, "children", []):
        
            self.analyse_node(child)

    def analyse_var_decl(self, node: VarDecl):
        self.current_scope.declare(node.name, node.type, node.pos)
        if node.value is not None:
            node_type = self.get_node_type(node)
            value_type = self.get_node_type(node.value)
            if not self.type_match(node_type, value_type):
                fbusl_error(
                    f'Variable "{node.name}" of type {node_type} cannot be set to value of type {value_type}',
                    node.pos,
                )

    def analyse_setter(self, node: Setter):
        node_type = self.get_node_type(node.node)
        val_type = self.get_node_type(node.value)

        if not self.type_match(node_type, val_type):
            fbusl_error(
                f'Cannot set variable "{node.node.value}" of type {node_type} to value of type "{val_type}"',
                node.pos,
            )

    def analyse_input(self, node: Input):
        self.current_scope.declare(node.name, node.type, node.pos, False)

    def analyse_output(self, node: Output):
        self.current_scope.declare(node.name, node.type, node.pos)

    def analyse_uniform(self, node: Uniform):
        self.current_scope.declare(node.name, node.type, node.pos, False)

    def analyse_struct_def(self, node: StructDef):
        fields = {field.name: field.type for field in node.fields}
        type_data = {"fields": fields}
        self.create_type(node.name, type_data, node.pos)

        self.define_function(node.name, {"name": node.name}, fields, {}, node.pos)

    def analyse_function_def(self, node: FunctionDef):
        params = {param.name: param.type for param in node.params}
        self.define_function(node.name, node.type, params, {}, node.pos)
        
        self.enter_scope()

        for node in node.body:
            self.analyse_node(node)

        self.exit_scope()

    def find_node_at_position(self, line: int, column: int):
        def recurse(node):
            pos = node.pos
            if pos.line == line and pos.start <= column <= pos.end:
                for child in getattr(node, "children", []):
                    found = recurse(child)
                    if found:
                        return found
                return node
            return None

        for node in self.tree:
            found = recurse(node)
            if found:
                return found

        return None

    def analyse_function_call(self, node: FuncCall):
        function = self.functions.get(node.name)
        if function is None:
            fbusl_error(f"Function '{node.name}' not defined", node.pos)

        arg_types = [self.get_type_name(self.get_node_type(arg)) for arg in node.args]

        overloads = function.get("overloads", [])
        if overloads and len(overloads) > 0:
            for overload in overloads:
                params = {
                    k: self.get_type_name(v)
                    for k, v in overload.get("params", {}).items()
                }
                if len(params) != len(arg_types):
                    continue

                match = True
                for (param_name, expected_type), actual_type in zip(
                    params.items(), arg_types
                ):
                    if not self.type_match(expected_type, actual_type):
                        match = False
                        break

                if match:
                    return self.get_type_name(
                        overload.get("return", function.get("type"))
                    )

            sigs = [
                "("
                + ", ".join(
                    self.get_type_name(p) for p in overload.get("params", {}).values()
                )
                + ")"
                for overload in overloads
            ]
            fbusl_error(
                f"No matching overload for function '{node.name}' with argument types ({', '.join(arg_types)}). ",
                node.pos,
            )

        else:
            params = {
                k: self.get_type_name(v) for k, v in function.get("params", {}).items()
            }
            if len(params) != len(arg_types):
                fbusl_error(
                    f"Function '{node.name}' expects {len(params)} arguments but got {len(arg_types)}",
                    node.pos,
                )

            for (param_name, expected_type), actual_type in zip(
                params.items(), arg_types
            ):
                if not self.type_match(expected_type, actual_type):
                    fbusl_error(
                        f"In call to '{node.name}', parameter '{param_name}' expects type '{expected_type}' "
                        f"but got '{actual_type}'",
                        node.pos,
                    )

            return self.get_type_name(function["type"])

    def enter_scope(self):
        self.current_scope = Scope(parent=self.current_scope)

    def exit_scope(self):
        if self.current_scope.parent:
            self.current_scope = self.current_scope.parent