"""Geometry-shader emulation, for backends (or devices) with no geometry
stage of their own.

`emulate()` rewrites a vertex + geometry shader pair into ordinary programs
that any backend's generator compiles like hand-written FBUSL. There are two
ways to do it, and `choose_mode()` picks between them:

"pull" - a single vertex shader (vertex pulling). The draw issues
    `primitives * slots` vertices with no vertex buffers, where `slots` is
    the most vertices the geometry stage can produce for one input
    primitive, as an independent list (triangles, lines or points). Vertex
    `i` works out its input primitive and output slot from VERTEX_INDEX,
    fetches that primitive's vertices from buffers (`gs_index`,
    `gs_attr_<input>`), runs the user's vertex shader on each, then runs
    the whole geometry shader and keeps only the vertex that lands in its
    slot. Strips become lists on the way: a 3-vertex window (2 for lines)
    follows the emitted vertices, and each completed triangle is numbered,
    with odd triangles in a strip swapping their first two vertices as GL
    does. A slot nothing was emitted for is moved outside the clip volume.
    Works everywhere a vertex shader can read buffers; the geometry shader
    runs `slots` times per primitive, so it suits small `max_vertices`.

"compute" - a compute pre-pass plus a pass-through vertex shader. One
    invocation per input primitive runs the vertex shader on its vertices
    and the geometry shader once, appending each completed primitive to
    `gs_out` (position, then every geometry @output, as floats - integer
    outputs are converted, exact up to 2^24) at a slot
    reserved with atomic_add on `gs_draw.data[0]` - laid out as an
    indirect draw command, {vertex count, instance count, first vertex,
    first instance}, so the backend draws exactly what was emitted with no
    readback. Needs real compute with atomics.

Both keep GL's semantics: the vertex shader's @outputs reach the geometry
shader's @inputs by position, each as an array with one element per input
vertex; input_position(i) is that vertex's VERTEX_POSITION; the geometry
shader's @outputs reach the fragment shader in declaration order.

The backend supplies, per draw: `_gs_prim_count` (input primitives),
`_gs_index_mode` (0: no index buffer, vertex i is i; 1: 16-bit indices,
two per int; 2: 32-bit indices) and, for "compute", `_gs_capacity` (output
vertices `gs_out` holds). `Emulation` describes everything else it needs:
which mesh attribute feeds which `gs_attr_*` buffer, the output layout,
the topology to draw and how many vertices.
"""
from dataclasses import dataclass, field

from fbusl import ShaderType, fbusl_error
from fbusl.node import (
    ASTNode, BufferBlock, Define, FuncCall, FunctionDef, Identifier, Input, Output, StructDef, Uniform,
    ArrayAccess, VarDecl,
)
from fbusl.parser import Lexer, Parser

INPUT_VERTICES = {"points": 1, "lines": 2, "lines_adjacency": 4, "triangles": 3, "triangles_adjacency": 6}
# Vertices per output primitive once strips are split into lists.
OUTPUT_VERTICES = {"points": 1, "line_strip": 2, "triangle_strip": 3}
OUTPUT_LIST = {"points": "points", "line_strip": "lines", "triangle_strip": "triangles"}

SCALARS = {
    "float": ("float", 1), "vec2": ("float", 2), "vec3": ("float", 3), "vec4": ("float", 4),
    "int": ("int", 1), "ivec2": ("int", 2), "ivec3": ("int", 3), "ivec4": ("int", 4),
}
# Above this many output vertex slots per primitive, re-running the
# geometry shader once per slot costs more than a compute pre-pass.
PULL_SLOT_LIMIT = 12
LOCAL_SIZE = 64


@dataclass
class Emulation:
    mode: str                      # "pull" or "compute"
    program: list                  # the vertex ("pull") or compute ("compute") program, unanalysed
    program_stage: ShaderType
    passthrough: list | None       # "compute": the vertex shader that draws gs_out
    input_primitive: str           # the geometry stage's input=
    input_vertices: int            # vertices per input primitive
    output_primitive: str          # "triangles", "lines" or "points" - what gets drawn
    output_vertices: int           # vertices per output primitive (3, 2, 1)
    max_primitives: int            # output primitives per input primitive, at most
    slots: int                     # output vertices per input primitive, at most
    attributes: list = field(default_factory=list)   # [(vertex @input name, type, scalar, components)]
    outputs: list = field(default_factory=list)      # [(geometry @output name, type, float offset, components)]
    stride: int = 0                # "compute": floats per gs_out vertex
    local_size: int = LOCAL_SIZE


def _type_text(t) -> str:
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        if t.get("name") == "array":
            data = t["data"]
            return f"{_type_text(data['base_type'])}[{data['length']}]"
        return t.get("name", "unknown")
    fbusl_error(f"Can't express type {t!r} in emulated geometry code.")


def _zero(t: str) -> str:
    scalar, n = SCALARS[t]
    one = "0.0" if scalar == "float" else "0"
    return one if n == 1 else f"{t}({', '.join([one] * n)})"


def _rewrite(node, fn, memo=None):
    """Rebuilds `node` bottom-up: every ASTNode reachable through its
    attributes (and lists of them) is passed through `fn`, which returns a
    replacement or the node itself. Shared references (FBUSL keeps nodes in
    both `children` and named fields) get the same replacement."""
    memo = {} if memo is None else memo
    if isinstance(node, list):
        return [_rewrite(n, fn, memo) for n in node]
    if not isinstance(node, ASTNode):
        return node
    if id(node) in memo:
        return memo[id(node)]
    memo[id(node)] = node  # breaks cycles; replaced below
    for key, value in list(vars(node).items()):
        if key in ("pos", "scope", "metadata", "type"):
            continue
        if isinstance(value, ASTNode) or (isinstance(value, list) and any(isinstance(v, ASTNode) for v in value)):
            setattr(node, key, _rewrite(value, fn, memo))
    result = fn(node)
    memo[id(node)] = result
    return result


def _renamer(identifiers: dict, calls: dict, input_position: str | None = None):
    def fn(node):
        if isinstance(node, Identifier) and node.value in identifiers:
            node.value = identifiers[node.value]
        elif isinstance(node, FuncCall):
            if input_position is not None and node.name == "input_position":
                return ArrayAccess(Identifier(input_position, node.pos), node.args[0], node.pos)
            if node.name in calls:
                node.name = calls[node.name]
        elif isinstance(node, FunctionDef) and node.name in calls:
            node.name = calls[node.name]
        return node
    return fn


def _parse(source: str) -> list:
    return Parser(Lexer(source, "<emulated geometry>").tokenize()).parse()


def _entry(tree, stage):
    if stage == "geometry":
        found = [n for n in tree if isinstance(n, FunctionDef) and n.stage == "geometry"]
        what = "@geometry entry function"
    else:
        found = [n for n in tree if isinstance(n, FunctionDef) and n.name == "main"]
        what = "`def main()`"
    if not found:
        fbusl_error(f"The {stage} shader has no {what}.")
    return found[0]


def _uses(tree, *, identifier=None, call=None) -> bool:
    hit = []

    def fn(node):
        if identifier is not None and isinstance(node, Identifier) and node.value == identifier:
            hit.append(node)
        if call is not None and isinstance(node, FuncCall) and node.name == call:
            hit.append(node)
        return node
    _rewrite(tree, fn)
    return bool(hit)


def geometry_args(geometry_tree) -> dict:
    return dict(_entry(geometry_tree, "geometry").stage_args)


def choose_mode(vertex_tree, geometry_tree, has_atomic_compute: bool) -> str:
    """"compute" when it can run there and the geometry stage is big enough
    for the pre-pass to win; "pull" otherwise."""
    args = geometry_args(geometry_tree)
    slots = _max_primitives(args) * OUTPUT_VERTICES[args["output"]]
    textures = any(isinstance(n, Uniform) and _type_text(n.type) in ("texture", "textureStack")
                   for n in vertex_tree + geometry_tree)
    instanced = _uses(vertex_tree, identifier="INSTANCE_ID")
    if has_atomic_compute and slots > PULL_SLOT_LIMIT and not textures and not instanced:
        return "compute"
    return "pull"


def _max_primitives(args) -> int:
    mv = int(args["max_vertices"])
    return {"points": mv, "line_strip": max(mv - 1, 0), "triangle_strip": max(mv - 2, 0)}[args["output"]]


def emulate(vertex_tree: list, geometry_tree: list, mode: str) -> Emulation:
    """`vertex_tree`/`geometry_tree`: parsed (injected, not yet analysed)
    FBUSL. Both are consumed - their nodes are moved into the result."""
    if mode not in ("pull", "compute"):
        fbusl_error(f"Unknown geometry emulation mode {mode!r}.")
    args = geometry_args(geometry_tree)
    n_in = INPUT_VERTICES[args["input"]]
    k = OUTPUT_VERTICES[args["output"]]
    max_prims = _max_primitives(args)
    slots = max_prims * k

    v_entry = _entry(vertex_tree, "vertex")
    g_entry = _entry(geometry_tree, "geometry")
    v_inputs = [n for n in vertex_tree if isinstance(n, Input)]
    v_outputs = [n for n in vertex_tree if isinstance(n, Output)]
    g_inputs = [n for n in geometry_tree if isinstance(n, Input)]
    g_outputs = [n for n in geometry_tree if isinstance(n, Output)]
    if len(g_inputs) > len(v_outputs):
        fbusl_error(f"The geometry shader reads {len(g_inputs)} @inputs but the vertex shader writes "
                    f"only {len(v_outputs)} @outputs.")

    attributes = []
    for node in v_inputs:
        t = _type_text(node.type)
        if t not in SCALARS:
            fbusl_error(f"Vertex @input '{node.name}: {t}' can't be fetched by emulated geometry shaders - "
                        f"use float/int scalars or vectors.")
        attributes.append((node.name, t, *SCALARS[t]))
    out_info, offset = [], 4
    for node in g_outputs:
        t = _type_text(node.type)
        if t not in SCALARS:
            fbusl_error(f"Geometry @output '{node.name}: {t}' must be a float/int scalar or vector.")
        out_info.append((node.name, t, offset, SCALARS[t][1]))
        offset += SCALARS[t][1]

    # -- rename the user's code into one program's namespace ----------------
    v_ids = {node.name: f"_gs_vin_{node.name}" for node in v_inputs}
    v_ids.update({node.name: f"_gs_vout_{i}" for i, node in enumerate(v_outputs)})
    v_ids["VERTEX_POSITION"] = "_gs_vpos"
    v_ids["VERTEX_INDEX"] = "_gs_vertex_id"
    if mode == "compute":
        v_ids["INSTANCE_ID"] = "_gs_instance_id"
    v_funcs = [n for n in vertex_tree if isinstance(n, FunctionDef) and n is not v_entry]
    g_funcs = [n for n in geometry_tree if isinstance(n, FunctionDef) and n is not g_entry]
    v_names = {f.name for f in v_funcs}
    g_calls = {f.name: f"_gs_gfn_{f.name}" for f in g_funcs if f.name in v_names}
    g_calls.update({"EmitVertex": "_gs_emit", "EndPrimitive": "_gs_end"})
    g_ids = {node.name: f"_gs_g_{node.name}" for node in g_outputs}
    g_ids["VERTEX_POSITION"] = "_gs_gpos"
    vertex_tree = _rewrite(vertex_tree, _renamer(v_ids, {}))
    geometry_tree = _rewrite(geometry_tree, _renamer(g_ids, g_calls, input_position="_gs_in_pos"))

    # -- glue, as FBUSL source ------------------------------------------------
    window = k
    g = []  # globals - before any decorator, which would absorb them
    for name, t, _, _ in attributes:
        g.append(f"_gs_vin_{name}: {t}")
    for i, node in enumerate(v_outputs):
        g.append(f"_gs_vout_{i}: {_type_text(node.type)}")
    for i, node in enumerate(g_inputs):
        g.append(f"{node.name}: {_type_text(node.type)}[{n_in}]")
    g += ["_gs_vpos: vec4", "_gs_gpos: vec4", "_gs_vertex_id: int", f"_gs_in_pos: vec4[{n_in}]",
          f"_gs_w_pos: vec4[{window}]", "_gs_strip: int", "_gs_prims: int"]
    for name, t, _, _ in out_info:
        g.append(f"_gs_g_{name}: {t}")
        g.append(f"_gs_w_{name}: {t}[{window}]")
    if mode == "compute":
        g.append("_gs_instance_id: int")
    else:
        g += ["_gs_target: int", "_gs_corner: int", "_gs_found: bool", "_gs_r_pos: vec4"]
        g += [f"_gs_r_{name}: {t}" for name, t, _, _ in out_info]

    d = ["readonly buffer gs_index:", "    data: int[1]"]
    for name, t, scalar, _ in attributes:
        d += [f"readonly buffer gs_attr_{name}:", f"    data: {scalar}[1]"]
    if mode == "compute":
        d += ["readwrite buffer gs_out:", "    data: float[1]", "readwrite buffer gs_draw:", "    data: int[1]"]
    d += ["@uniform", "_gs_prim_count: int", "_gs_index_mode: int"]
    if mode == "compute":
        d.append("_gs_capacity: int")
    if mode == "pull":
        d.append("@output")
        d += [f"{name}: {t}" for name, t, _, _ in out_info]

    f = []  # functions the user's code calls (declared before it)
    lines = []
    for i in range(window - 1):
        lines.append(f"    _gs_w_pos[{i}] = _gs_w_pos[{i + 1}]")
        for name, _, _, _ in out_info:
            lines.append(f"    _gs_w_{name}[{i}] = _gs_w_{name}[{i + 1}]")
    lines.append(f"    _gs_w_pos[{window - 1}] = _gs_gpos")
    for name, _, _, _ in out_info:
        lines.append(f"    _gs_w_{name}[{window - 1}] = _gs_g_{name}")
    lines.append("    _gs_strip += 1")
    lines.append(f"    if _gs_strip >= {k}:")
    if mode == "pull":
        lines += ["        if _gs_prims == _gs_target:",
                  "            c: int = _gs_corner"]
        if k == 3:
            lines += ["            if (_gs_strip - 3) % 2 == 1 and c < 2:",
                      "                c = 1 - c"]
        lines.append("            _gs_r_pos = _gs_w_pos[c]")
        lines += [f"            _gs_r_{name} = _gs_w_{name}[c]" for name, _, _, _ in out_info]
        lines.append("            _gs_found = True")
    else:
        lines += [f"        base: int = atomic_add(gs_draw.data[0], {k})",
                  f"        if base + {k} <= _gs_capacity:",
                  "            c: int = 0",
                  f"            while c < {k}:",
                  "                src: int = c"]
        if k == 3:
            lines += ["                if (_gs_strip - 3) % 2 == 1 and c < 2:",
                      "                    src = 1 - c"]
        lines.append(f"                o: int = (base + c) * {offset}")
        for comp, ch in enumerate("xyzw"):
            lines.append(f"                gs_out.data[o + {comp}] = _gs_w_pos[src].{ch}")
        for name, t, off, n in out_info:
            as_float = "float({})" if SCALARS[t][0] == "int" else "{}"
            if n == 1:
                value = as_float.format(f"_gs_w_{name}[src]")
                lines.append(f"                gs_out.data[o + {off}] = {value}")
            else:
                for comp, ch in enumerate("xyzw"[:n]):
                    value = as_float.format(f"_gs_w_{name}[src].{ch}")
                    lines.append(f"                gs_out.data[o + {off + comp}] = {value}")
        lines.append("                c += 1")
    lines.append("        _gs_prims += 1")
    f.append("def _gs_emit():\n" + "\n".join(lines))
    f.append("def _gs_end():\n    _gs_strip = 0")
    f.append("""def _gs_index(i: int) -> int:
    if _gs_index_mode == 0:
        return i
    if _gs_index_mode == 1:
        word: int = gs_index.data[i / 2]
        if i % 2 == 1:
            return (word >> 16) & 65535
        return word & 65535
    return gs_index.data[i]""")
    fetch = ["def _gs_fetch(v: int):", "    _gs_vertex_id = v"]
    for name, t, scalar, n in attributes:
        buf = f"gs_attr_{name}.data"
        if n == 1:
            fetch.append(f"    _gs_vin_{name} = {buf}[v]")
        else:
            parts = ", ".join(f"{buf}[v * {n} + {c}]" for c in range(n))
            fetch.append(f"    _gs_vin_{name} = {t}({parts})")
    f.append("\n".join(fetch))
    f.append("def _gs_vs():\n    _gs_vpos = _gs_vpos")   # body replaced by the vertex shader's main
    f.append("def _gs_gs():\n    _gs_gpos = _gs_gpos")   # body replaced by the geometry shader's entry

    load = ["def _gs_load(prim: int):",
            "    k: int = 0",
            f"    while k < {n_in}:",
            f"        _gs_fetch(_gs_index(prim * {n_in} + k))",
            "        _gs_vs()",
            "        _gs_in_pos[k] = _gs_vpos"]
    for i, node in enumerate(g_inputs):
        load.append(f"        {node.name}[k] = _gs_vout_{i}")
    load.append("        k += 1")
    tail = ["\n".join(load)]

    if mode == "pull":
        main = ["def main():",
                f"    prim: int = VERTEX_INDEX / {slots}",
                f"    slot: int = VERTEX_INDEX - prim * {slots}",
                f"    _gs_target = slot / {k}",
                f"    _gs_corner = slot - _gs_target * {k}",
                "    _gs_found = False",
                "    _gs_strip = 0",
                "    _gs_prims = 0",
                # Outside the clip volume (past the far plane): a slot nothing
                # was emitted for draws nothing, even as a point.
                "    _gs_r_pos = vec4(0.0, 0.0, 2.0, 1.0)"]
        main += [f"    _gs_r_{name} = {_zero(t)}" for name, t, _, _ in out_info]
        main += ["    if prim < _gs_prim_count:",
                 "        _gs_load(prim)",
                 "        _gs_gs()"]
        main += [f"    {name} = _gs_r_{name}" for name, _, _, _ in out_info]
        main.append("    VERTEX_POSITION = _gs_r_pos")
        tail.append("\n".join(main))
    else:
        tail.append("\n".join([
            f"@compute(local_size_x={LOCAL_SIZE})",
            "def main():",
            "    prim: int = GLOBAL_INVOCATION_ID.x",
            "    _gs_instance_id = 0",
            "    _gs_strip = 0",
            "    _gs_prims = 0",
            "    if prim < _gs_prim_count:",
            "        _gs_load(prim)",
            "        _gs_gs()"]))

    head = _parse("\n".join(g) + "\n\n" + "\n".join(d) + "\n\n" + "\n\n".join(f) + "\n")
    tail_nodes = _parse("\n\n".join(tail) + "\n")
    funcs = {n.name: n for n in head if isinstance(n, FunctionDef)}
    funcs["_gs_vs"].body = v_entry.body
    funcs["_gs_vs"].children = list(v_entry.body)
    funcs["_gs_gs"].body = g_entry.body
    funcs["_gs_gs"].children = list(g_entry.body)

    # -- assemble: declarations first, then the user's helpers, then glue ----
    globals_ = [n for n in head if not isinstance(n, (FunctionDef, BufferBlock, Uniform, Output))]
    decls = [n for n in head if isinstance(n, (BufferBlock, Uniform, Output))]
    seen_structs, seen_uniforms, seen_defines = set(), {n.name for n in decls if isinstance(n, Uniform)}, set()
    user_decls = []
    for tree in (vertex_tree, geometry_tree):
        for node in tree:
            if isinstance(node, StructDef) and node.name not in seen_structs:
                seen_structs.add(node.name)
                user_decls.append(node)
            elif isinstance(node, Uniform) and node.name not in seen_uniforms:
                seen_uniforms.add(node.name)
                user_decls.append(node)
            elif isinstance(node, Define) and node.name not in seen_defines:
                seen_defines.add(node.name)
                user_decls.append(node)
            elif isinstance(node, BufferBlock):
                user_decls.append(node)
            elif isinstance(node, VarDecl):
                # The user's own globals (a geometry shader keeping state
                # between helper calls, say) - with the glue's, ahead of
                # every decorator.
                globals_.append(node)
    order = ["_gs_emit", "_gs_end", "_gs_index", "_gs_fetch"]
    program = (globals_ + user_decls + decls + [funcs[n] for n in order] + v_funcs + [funcs["_gs_vs"]]
               + g_funcs + [funcs["_gs_gs"]] + tail_nodes)

    passthrough = None
    if mode == "compute":
        def stored(t):  # what gs_out holds for a `t` output: floats throughout
            n = SCALARS[t][1]
            return "float" if n == 1 else f"vec{n}"

        src = ["@input", "_gs_p_pos: vec4"] + [f"_gs_p_{name}: {stored(t)}" for name, t, _, _ in out_info]
        src += ["@output"] + [f"{name}: {t}" for name, t, _, _ in out_info]
        src += ["", "def main():"]
        for name, t, _, n in out_info:
            if SCALARS[t][0] == "float":
                src.append(f"    {name} = _gs_p_{name}")
            elif n == 1:
                src.append(f"    {name} = int(_gs_p_{name})")
            else:
                parts = ", ".join(f"int(_gs_p_{name}.{ch})" for ch in "xyzw"[:n])
                src.append(f"    {name} = {t}({parts})")
        src.append("    VERTEX_POSITION = _gs_p_pos")
        passthrough = _parse("\n".join(src) + "\n")

    return Emulation(
        mode=mode, program=program,
        program_stage=ShaderType.VERTEX if mode == "pull" else ShaderType.COMPUTE,
        passthrough=passthrough, input_primitive=args["input"], input_vertices=n_in,
        output_primitive=OUTPUT_LIST[args["output"]], output_vertices=k, max_primitives=max_prims,
        slots=slots, attributes=attributes, outputs=out_info, stride=offset if mode == "compute" else 0)
