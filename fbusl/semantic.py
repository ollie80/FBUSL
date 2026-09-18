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
            p_vars = self.parent.get_all_vars()
        return p_vars | self.variables.copy()

    def declare(
        self, name: str, var_type, position: Position, mutable=True, initialized=True
    ):
        if name in self.variables:
            fbusl_error(
                f"Variable '{name}' already declared in this scope",
                position
            )

        self.variables[name] = {
            "type": var_type,
            "mutable": mutable,
            "initialized": initialized,
        }

    def initialize_variable(self, name):
        if name not in self.variables:
            fbusl_error(
                f"Variable '{name}' is not delcared in this scope."
            )

        self.variables[name]["initialized"] = True

    def exists(self, name) -> bool:
        if name in self.variables:
            return True

        if self.parent:
            return self.parent.exists(name)

        return False

    def lookup(self, name: str, pos: Position):
        if name in self.variables:
            return self.variables[name]

        if self.parent:
            return self.parent.lookup(name, pos)

        fbusl_error(
            f"Variable '{name}' not defiened in current scope.",
            pos
        )


class SemanticAnalyser:
    def __init__(
        self,
        tree: list[ASTNode],
        shader_type: ShaderType,
        extra_builtins={}
    ):
        self.tree = tree
        self.shader_type = shader_type
        self.global_scope = Scope()
        self.types = TYPES.copy()

        self.current_scope = self.global_scope
        self.functions = {}

        self.define_builtins(extra_builtins)

    def define_builtins(self, extra):
        builtins: dict = (
            BUILTINS.get("all", {})
            | BUILTINS.get(self.shader_type, {})
            | extra
        )

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

            elif kind in ("output", "uniform", "variable"):
                self.current_scope.declare(
                    builtin_name,
                    builtin_data.get("type"),
                    Position(),
                    mutable=(kind != "uniform"),
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
            fbusl_error(
                f"Function '{name}' already defined",
                pos
            )

        self.functions[name] = {
            "type": return_type,
            "params": params,
            "overloads": overloads,
        }

    def create_type(self, name: str, data: dict, pos: Position):
        if name in self.types:
            fbusl_error(
                f'Type "{name}" already exists.',
                pos
            )

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
        self,
        op: str,
        left: ASTNode,
        right: ASTNode,
        pos: Position
    ) -> str:
        left_type = self.get_node_type(left)
        right_type = self.get_node_type(right)

        left_def = self.types.get(left_type)

        if not left_def:
            fbusl_error(
                f"Unknown type '{left_type}' in binary operation",
                pos
            )
            return "unknown"

        operations = left_def.get("operations", {})
        rules = operations.get(op)

        if not rules:
            fbusl_error(
                f"Type '{left_type}' does not support operator '{op}'",
                pos
            )
            return "unknown"

        result_type = rules.get(right_type)

        if not result_type:
            fbusl_error(
                f"Operator '{op}' not supported between '{left_type}' and '{right_type}'",
                pos
            )
            return "unknown"

        return result_type

    def set_node_types(self, node: ASTNode) -> str:
        if node is None:
            return

        if isinstance(node, FunctionDef):
            previous_scope = self.current_scope

            self.current_scope = node.scope

            for stmt in node.body:
                self.set_node_types(stmt)

            node.type = self.get_node_type(node)

            self.current_scope = previous_scope
            return node.type

        if isinstance(node, VarDecl):
            if node.value:
                self.set_node_types(node.value)

            value_type = None

            if node.value:
                value_type = self.get_node_type(node.value)

            node.type = self.get_type_name(node.type)

            if value_type is not None and not self.type_match(
                node.type,
                value_type
            ):
                fbusl_error(
                    f'Variable "{node.name}" of type {node.type} cannot be set to value of type {value_type}',
                    node.pos,
                )

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

        elif isinstance(node, ArrayAccess):
            self.set_node_types(node.base)
            self.set_node_types(node.index)
            node.type = self.get_node_type(node)

        elif isinstance(node, FuncCall):
            for arg in node.args:
                self.set_node_types(arg)

            node.type = self.get_node_type(node)

        elif isinstance(node, StructDef):
            for field in node.fields:
                self.set_node_types(field)

            node.type = self.get_node_type(node)

        elif isinstance(node, BufferBlock):
            for field in node.fields:
                self.set_node_types(field)

            node.type = node.name

        elif isinstance(node, SharedDecl):
            node.type = self.get_type_name(node.type)

        elif isinstance(node, Output):
            node.type = self.get_node_type(node)

        elif isinstance(node, Input):
            node.type = self.get_node_type(node)

        elif isinstance(node, Uniform):
            node.type = self.get_node_type(node)

        elif getattr(node, "children", None):
            for child in node.children:
                if child is not None:
                    self.set_node_types(child)

            node.type = self.get_node_type(node)

        return node.type

    def get_node_type(self, node: ASTNode) -> str:
        if node is None:
            return "unknown"

        if isinstance(node, VarDecl):
            return self.get_type_name(node.type)

        elif isinstance(node, Identifier):
            var = self.current_scope.lookup(
                node.value,
                node.pos
            )

            if var is None:
                return "unknown"

            return self.get_type_name(var["type"])

        elif isinstance(node, Literal):
            return self.get_type_name(node.type)

        elif isinstance(node, Setter):
            return self.get_node_type(node.value)

        elif isinstance(node, BinOp):
            return self.get_binop_type(
                node.op,
                node.left,
                node.right,
                node.pos
            )

        elif isinstance(node, UnaryOp):
            return self.get_node_type(node.operand)

        elif isinstance(node, InlineIf):
            return self.get_node_type(node.then_expr)

        elif isinstance(node, MemberAccess):
            base_type = self.get_type_name(
                self.get_node_type(node.base)
            )

            struct_def = self.types.get(base_type)

            if struct_def:
                field_type = struct_def.get("fields", {}).get(
                    node.member
                )

                if field_type is None:
                    fbusl_error(
                        f"Struct '{base_type}' has no member '{node.member}'",
                        node.pos
                    )

                return self.get_type_name(field_type)

            fbusl_error(
                f"Cannot access member '{node.member}' on type '{base_type}'",
                node.pos
            )

        elif isinstance(node, FuncCall):
            return self.analyse_function_call(node)
        elif isinstance(node, StructDef):
            return node.name

        elif isinstance(node, ArrayAccess):
            # get_node_type(node.base) alone would collapse an array-typed
            # base straight to the bare string "array" (see MemberAccess/
            # Identifier below: both stringify via get_type_name, which
            # discards a type dict's "data" payload), losing the element
            # type entirely. _get_raw_type() keeps the raw {"name": "array",
            # "data": {...}} dict around long enough for indexing to unwrap
            # it to the actual element type.
            base_raw = self._get_raw_type(node.base)
            if isinstance(base_raw, dict) and base_raw.get("name") == "array":
                return self.get_type_name(base_raw["data"]["base_type"])
            return self.get_node_type(node.base)

        elif hasattr(node, "type"):
            return self.get_type_name(node.type)

        return "unknown"

    def _get_raw_type(self, node: ASTNode):
        """Like get_node_type, but for an Identifier/MemberAccess returns the
        raw declared type representation (a dict for a struct/array-shaped
        type, a string for a scalar) instead of collapsing it to just its
        type name. Only ArrayAccess needs this - everywhere else, the
        stringified name from get_node_type is exactly what's wanted.
        """
        if isinstance(node, Identifier):
            var = self.current_scope.lookup(node.value, node.pos)
            return var["type"] if var is not None else "unknown"

        if isinstance(node, MemberAccess):
            base_type = self.get_type_name(self.get_node_type(node.base))
            struct_def = self.types.get(base_type)
            if struct_def:
                field_type = struct_def.get("fields", {}).get(node.member)
                if field_type is not None:
                    return field_type
            return "unknown"

        return self.get_node_type(node)

    def type_match(self, t1: str, t2: str):
        return t1 == t2

    def analyse_node(self, node: ASTNode):
        if node is None:
            return

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

        elif isinstance(node, BufferBlock):
            self.analyse_buffer_block(node)

        elif isinstance(node, SharedDecl):
            self.current_scope.declare(node.name, node.type, node.pos)

        elif isinstance(node, Setter):
            self.analyse_setter(node)

        elif isinstance(node, FunctionDef):
            self.analyse_function_def(node)
            return

        elif isinstance(node, FuncCall):
            self.analyse_function_call(node)

        for child in getattr(node, "children", []):
            if child is not None:
                self.analyse_node(child)

    def analyse_var_decl(self, node: VarDecl):
        self.current_scope.declare(
            node.name,
            node.type,
            node.pos
        )

    def analyse_setter(self, node: Setter):
        target = node.node
        if isinstance(target, Identifier):
            var = self.current_scope.lookup(target.value, node.pos)
            if var is not None and not var.get("mutable", True):
                fbusl_error(
                    f"Cannot assign to '{target.value}': it is not mutable (declared as a uniform).",
                    node.pos,
                )

    def analyse_input(self, node: Input):
        self.current_scope.declare(
            node.name,
            node.type,
            node.pos,
            False
        )

    def analyse_output(self, node: Output):
        self.current_scope.declare(
            node.name,
            node.type,
            node.pos
        )

    def analyse_uniform(self, node: Uniform):
        self.current_scope.declare(
            node.name,
            node.type,
            node.pos,
            False
        )

    def analyse_struct_def(self, node: StructDef):
        fields = {
            field.name: field.type
            for field in node.fields
        }

        type_data = {
            "fields": fields
        }

        self.create_type(
            node.name,
            type_data,
            node.pos
        )

        self.define_function(
            node.name,
            {"name": node.name},
            fields,
            {},
            node.pos
        )

    def analyse_buffer_block(self, node: BufferBlock):
        fields = {
            field.name: field.type
            for field in node.fields
        }

        # A buffer block is registered as its own type, exactly like a
        # struct, so `Block.field[index]` flows through the same
        # MemberAccess/ArrayAccess type-inference code already used for
        # ordinary structs - but it's declared in scope as an instance of
        # itself (`{"name": node.name}`), not defined as a callable
        # constructor function: you write `Chunks.chunk_array[i]`, never
        # `Chunks(...)`.
        self.create_type(
            node.name,
            {"fields": fields},
            node.pos,
        )

        self.current_scope.declare(
            node.name,
            {"name": node.name},
            node.pos,
            mutable=False,
        )

    GEOMETRY_INPUT_PRIMITIVES = {"points", "lines", "lines_adjacency", "triangles", "triangles_adjacency"}
    GEOMETRY_OUTPUT_PRIMITIVES = {"points", "line_strip", "triangle_strip"}

    def _validate_geometry_stage_args(self, node: FunctionDef):
        args = node.stage_args
        input_prim = args.get("input")
        output_prim = args.get("output")
        max_vertices = args.get("max_vertices")

        if input_prim not in self.GEOMETRY_INPUT_PRIMITIVES:
            fbusl_error(
                f"@geometry 'input' must be one of {sorted(self.GEOMETRY_INPUT_PRIMITIVES)}, got {input_prim!r}",
                node.pos,
            )
        if output_prim not in self.GEOMETRY_OUTPUT_PRIMITIVES:
            fbusl_error(
                f"@geometry 'output' must be one of {sorted(self.GEOMETRY_OUTPUT_PRIMITIVES)}, got {output_prim!r}",
                node.pos,
            )
        if not isinstance(max_vertices, int):
            fbusl_error(
                f"@geometry 'max_vertices' must be an integer, got {max_vertices!r}",
                node.pos,
            )

    def _validate_compute_stage_args(self, node: FunctionDef):
        args = node.stage_args
        if "local_size_x" not in args:
            fbusl_error(f"@{node.stage} requires 'local_size_x'", node.pos)
        for axis in ("local_size_x", "local_size_y", "local_size_z"):
            args.setdefault(axis, 1)
            if not isinstance(args[axis], int):
                fbusl_error(f"@{node.stage} '{axis}' must be an integer, got {args[axis]!r}", node.pos)

        if node.stage == "raytrace":
            # Fixed traversal-stack depth for the BVH walk `trace_ray()`
            # lowers to - GLSL 330 has no recursion/dynamic-size arrays, so
            # this can never be truly dynamic (see GL33Generator's raytrace
            # IMPLEMENTATIONS entry).
            args.setdefault("max_stack", 32)
            if not isinstance(args["max_stack"], int):
                fbusl_error(f"@raytrace 'max_stack' must be an integer, got {args['max_stack']!r}", node.pos)

            # Separate from max_stack: the traversal loop's total node-visit
            # budget, not its stack-depth budget - see GL33Generator's
            # _generate_raytrace_intrinsics for why conflating the two
            # silently truncates traversal on any non-trivial BVH.
            args.setdefault("max_iterations", 4096)
            if not isinstance(args["max_iterations"], int):
                fbusl_error(f"@raytrace 'max_iterations' must be an integer, got {args['max_iterations']!r}", node.pos)

    def analyse_function_def(self, node: FunctionDef):
        if node.stage == "geometry":
            self._validate_geometry_stage_args(node)
        elif node.stage in ("compute", "raytrace"):
            self._validate_compute_stage_args(node)

        params = {
            param.name: param.type
            for param in node.params
        }

        self.define_function(
            node.name,
            node.type,
            params,
            {},
            node.pos
        )

        self.enter_scope()

        for param in node.params:
            self.current_scope.declare(
                param.name,
                param.type,
                param.pos
            )

        # Delegate to analyse_node for every top-level body statement instead of
        # only shallow-scanning for VarDecl: analyse_node already knows how to
        # declare a VarDecl, validate a Setter/FuncCall, and - for any node kind
        # it has no dedicated branch for (IfStatement, WhileStatement, ...) -
        # falls through to recursing into `node.children`, which is exactly how
        # those nodes hold their nested body statements. Without this, a VarDecl
        # or FuncCall nested inside an `if`/`elif`/`else` body was never scoped
        # or checked at all.
        for stmt in node.body:
            self.analyse_node(stmt)

        node.scope = self.current_scope

        self.exit_scope()

    def find_node_at_position(self, line: int, column: int):
        def recurse(node):
            if node is None:
                return None

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
            fbusl_error(
                f"Function '{node.name}' not defined",
                node.pos
            )
            return "unknown"

        arg_types = [
            self.get_type_name(
                self.get_node_type(arg)
            )
            for arg in node.args
        ]

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
                    params.items(),
                    arg_types
                ):
                    if not self.type_match(
                        expected_type,
                        actual_type
                    ):
                        match = False
                        break

                if match:
                    return self.get_type_name(
                        overload.get(
                            "return",
                            function.get("type")
                        )
                    )

            fbusl_error(
                f"No matching overload for function '{node.name}' "
                f"with argument types ({', '.join(arg_types)}). ",
                node.pos,
            )
            return "unknown"

        else:
            params = {
                k: self.get_type_name(v)
                for k, v in function.get("params", {}).items()
            }

            if len(params) != len(arg_types):
                fbusl_error(
                    f"Function '{node.name}' expects "
                    f"{len(params)} arguments but got {len(arg_types)}",
                    node.pos
                )

            for (param_name, expected_type), actual_type in zip(
                params.items(),
                arg_types
            ):
                if not self.type_match(
                    expected_type,
                    actual_type
                ):
                    fbusl_error(
                        f"In call to '{node.name}', parameter "
                        f"'{param_name}' expects type '{expected_type}' "
                        f"but got '{actual_type}'",
                        node.pos
                    )

            return self.get_type_name(
                function["type"]
            )

    def enter_scope(self):
        self.current_scope = Scope(
            parent=self.current_scope
        )

    def exit_scope(self):
        if self.current_scope.parent:
            self.current_scope = self.current_scope.parent
