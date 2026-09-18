from itertools import product
from fbusl import ShaderType
from itertools import product

from itertools import product


def generate_overloads_with_cost(param_slots, allowed_types_map, max_cost=1):
    overloads = []
    type_list = list(allowed_types_map.keys())

    for n in range(1, len(param_slots) + 1):
        slots_subset = param_slots[:n]

        for combo in product(type_list, repeat=n):
            cost = sum(int(allowed_types_map[t]) for t in combo)

            if cost == max_cost:
                params = dict(zip(slots_subset, combo))
                overloads.append(
                    {
                        "params": params,
                        "cost": cost,
                    }
                )

    return overloads


TYPES = {
    "void": {"operations": {}},
    "int": {
        "operations": {
            "+": {"int": "int"},
            "-": {"int": "int"},
            "*": {"int": "int"},
            "/": {"int": "int"},
            "%": {"int": "int"},
            "&": {"int": "int"},
            "|": {"int": "int"},
            "^": {"int": "int"},
            "<<": {"int": "int"},
            ">>": {"int": "int"},
            "-_unary": {"": "int"},
            "+_unary": {"": "int"},
            "~": {"": "int"},
            "==": {"int": "bool"},
            "!=": {"int": "bool"},
            "<": {"int": "bool"},
            "<=": {"int": "bool"},
            ">": {"int": "bool"},
            ">=": {"int": "bool"},
        }
    },
    "float": {
        "operations": {
            "+": {"float": "float"},
            "-": {"float": "float"},
            "*": {"float": "float"},
            "/": {"float": "float"},
            "-_unary": {"": "float"},
            "+_unary": {"": "float"},
            "==": {"float": "bool"},
            "!=": {"float": "bool"},
            "<": {"float": "bool"},
            "<=": {"float": "bool"},
            ">": {"float": "bool"},
            ">=": {"float": "bool"},
        }
    },
    "vec2": {
        "fields": {"x": "float", "y": "float", "xy": "vec2", "yx": "vec2"},
        "operations": {
            "+": {"vec2": "vec2"},
            "-": {"vec2": "vec2"},
            "*": {"float": "vec2", "vec2": "vec2"},
            "/": {"float": "vec2", "vec2": "vec2"},
        },
    },
    "vec3": {
        "fields": {
            "x": "float",
            "y": "float",
            "z": "float",
            "xy": "vec2",
            "yx": "vec2",
            "yz": "vec2",
            "zy": "vec2",
            "xz": "vec2",
            "zx": "vec2",
            "xyz": "vec3",
            "xzy": "vec3",
            "yxz": "vec3",
            "yzx": "vec3",
            "zxy": "vec3",
            "zyx": "vec3",
        },
        "operations": {
            "+": {"vec3": "vec3"},
            "-": {"vec3": "vec3"},
            "*": {"float": "vec3", "vec3": "vec3"},
            "/": {"float": "vec3", "vec3": "vec3"},
        },
    },
    "vec4": {
        "fields": {
            "x": "float",
            "y": "float",
            "z": "float",
            "w": "float",
            "xy": "vec2",
            "xz": "vec2",
            "xw": "vec2",
            "yx": "vec2",
            "yz": "vec2",
            "yw": "vec2",
            "zx": "vec2",
            "zy": "vec2",
            "zw": "vec2",
            "wx": "vec2",
            "wy": "vec2",
            "wz": "vec2",
            "xyz": "vec3",
            "xzy": "vec3",
            "xwy": "vec3",
            "xwz": "vec3",
            "yxz": "vec3",
            "yzx": "vec3",
            "ywx": "vec3",
            "ywz": "vec3",
            "zxy": "vec3",
            "zyx": "vec3",
            "zwx": "vec3",
            "zwy": "vec3",
            "wxy": "vec3",
            "wyx": "vec3",
            "wzx": "vec3",
            "wzy": "vec3",
            "xyzw": "vec4",
            "xzyw": "vec4",
            "xwzy": "vec4",
            "xwyz": "vec4",
            "yxzw": "vec4",
            "yzxw": "vec4",
            "ywxz": "vec4",
            "ywzx": "vec4",
            "zxyw": "vec4",
            "zyxw": "vec4",
            "zwxy": "vec4",
            "zwyx": "vec4",
            "wxyz": "vec4",
            "wyxz": "vec4",
            "wzxy": "vec4",
            "wzyx": "vec4",
        },
        "operations": {
            "+": {"vec4": "vec4"},
            "-": {"vec4": "vec4"},
            "*": {"float": "vec4", "vec4": "vec4"},
            "/": {"float": "vec4", "vec4": "vec4"},
        },
    },
    "mat2": {
        "fields": {"col0": "vec2", "col1": "vec2"},
        "operations": {"*": {"float": "mat2", "vec2": "vec2", "mat2": "mat2"}},
    },
    "mat3": {
        "fields": {"col0": "vec3", "col1": "vec3", "col2": "vec3"},
        "operations": {"*": {"float": "mat3", "vec3": "vec3", "mat3": "mat3"}},
    },
    "mat4": {
        "fields": {"col0": "vec4", "col1": "vec4", "col2": "vec4", "col3": "vec4"},
        "operations": {"*": {"float": "mat4", "vec4": "vec4", "mat4": "mat4"}},
    },
    "texture": {},
    "textureStack": {},
    "array": {
        "data": {"base_type": str, "length": int},
        "operations": {"[]": lambda array_type: array_type["data"]["base_type"]},
    },
    "ivec2": {
        "fields": {"x": "int", "y": "int", "xy": "ivec2", "yx": "ivec2"},
        "operations": {},
    },
    "ivec3": {
        "fields": {
            "x": "int", "y": "int", "z": "int",
            "xy": "ivec2", "yx": "ivec2", "yz": "ivec2", "zy": "ivec2", "xz": "ivec2", "zx": "ivec2",
            "xyz": "ivec3", "xzy": "ivec3", "yxz": "ivec3", "yzx": "ivec3", "zxy": "ivec3", "zyx": "ivec3",
        },
        "operations": {},
    },
    # A GLSL image binding point (image2D/iimage2D/...). Read via image_load,
    # written via image_store - the latter needs a backend capability
    # ("compute.image_write") most backends (GL33 included) don't have.
    "image": {"operations": {}},
}

BUILTINS = {
    "all": {
        "round": {"return": "int", "params": {"x": "float"}, "kind": "function"},
        "abs": {
    "return": "float",
    "params": {"x": "float"},
    "kind": "function",
},
"length": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {"params": {"x": "vec2"}, "return": "float"},
        {"params": {"x": "vec3"}, "return": "float"},
    ],
},
# Vector/lighting math GLSL already provides natively under these exact
# names - no GL33Generator IMPLEMENTATIONS entry needed (the default
# function-call codegen already emits `name(args...)`, which is correct
# GLSL as-is). Needed for any real shading (normals, reflections, Fresnel,
# noise/hash) - a raytrace kernel can't do lighting at all without them.
"sqrt": {"return": "float", "params": {"x": "float"}, "kind": "function"},
"floor": {"return": "float", "params": {"x": "float"}, "kind": "function"},
"fract": {"return": "float", "params": {"x": "float"}, "kind": "function"},
"pow": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {"params": {"x": "float", "y": "float"}, "return": "float"},
        {"params": {"x": "vec3", "y": "vec3"}, "return": "vec3"},
    ],
},
"dot": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {"params": {"x": "vec2", "y": "vec2"}, "return": "float"},
        {"params": {"x": "vec3", "y": "vec3"}, "return": "float"},
    ],
},
"cross": {"return": "vec3", "params": {"x": "vec3", "y": "vec3"}, "kind": "function"},
"normalize": {"return": "vec3", "params": {"x": "vec3"}, "kind": "function"},
"reflect": {"return": "vec3", "params": {"i": "vec3", "n": "vec3"}, "kind": "function"},
"max": {
    "kind": "function",
    "overloads": [
        {"params": {"x": "float", "y": "float"}, "return": "float"},
        {"params": {"x": "vec2", "y": "vec2"}, "return": "vec2"},
        {"params": {"x": "vec3", "y": "vec3"}, "return": "vec3"},
        {"params": {"x": "vec4", "y": "vec4"}, "return": "vec4"},
    ],
    "return": "float",
},
"min": {
    "kind": "function",
    "overloads": [
        {"params": {"x": "float", "y": "float"}, "return": "float"},
        {"params": {"x": "vec2", "y": "vec2"}, "return": "vec2"},
        {"params": {"x": "vec3", "y": "vec3"}, "return": "vec3"},
        {"params": {"x": "vec4", "y": "vec4"}, "return": "vec4"},
    ],
    "return": "float",
},
"smoothstep": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {
            "params": {
                "edge0": "float",
                "edge1": "float",
                "x": "float",
            },
            "return": "float",
        },
    ],
},
"clamp": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {
            "params": {
                "x": "float",
                "min_val": "float",
                "max_val": "float",
            },
            "return": "float",
        },
        {
            "params": {
                "x": "vec2",
                "min_val": "float",
                "max_val": "float",
            },
            "return": "vec2",
        },
        {
            "params": {
                "x": "vec3",
                "min_val": "float",
                              "max_val": "float",
            },
            "return": "vec3",
        },
        {
            "params": {
                "x": "vec4",
                "min_val": "float",
                "max_val": "float",
            },
            "return": "vec4",
        },
    ],
},
"mix": {
    "kind": "function",
    "return": "float",
    "overloads": [
        {
            "params": {
                "x": "float",
                "y": "float",
                "a": "float",
            },
            "return": "float",
        },
        {
            "params": {
                "x": "vec2",
                "y": "vec2",
                "a": "float",
            },
            "return": "vec2",
        },
        {
            "params": {
                "x": "vec3",
                "y": "vec3",
                "a": "float",
            },
            "return": "vec3",
        },
        {
            "params": {
                "x": "vec4",
                "y": "vec4",
                "a": "float",
            },
            "return": "vec4",
        },
    ],
}, 
        "float": {"return": "float", "params": {"x": "int"}, "kind": "function"},
        "int": {"return": "int", "params": {"x": "float"}, "kind": "function"},
        "sin": {"return": "float", "params": {"x": "float"}, "kind": "function"},
        "cos": {"return": "float", "params": {"x": "float"}, "kind": "function"},
        "tan": {"return": "float", "params": {"x": "float"}, "kind": "function"},
        "sign": {"return": "float", "params": {"x": "float"}, "kind": "function"},
        "vec2": {
            "return": "vec2",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y"], {"float": 1, "vec2": "2"}, max_cost=2
            ),
        },
        "ivec2": {
            "return": "ivec2",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y"], {"int": 1, "ivec2": 2}, max_cost=2
            ),
        },
        "ivec3": {
            "return": "ivec3",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y", "z"], {"int": 1, "ivec2": 2, "ivec3": 3}, max_cost=3
            ),
        },
        "vec3": {
            "return": "vec3",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y", "z"], {"float": 1, "vec2": "2", "vec3": 3}, max_cost=3
            ),
        },
        "vec4": {
            "return": "vec4",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y", "z", "w"],
                {"float": 1, "vec2": 2, "vec3": 3, "vec4": 4},
                max_cost=4,
            ),
        },
        "mat2": {
            "return": "mat2",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {"params": {"col0": "vec2", "col1": "vec2"}},
            ],
        },
        "mat3": {
            "return": "mat3",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {"params": {"col0": "vec3", "col1": "vec3", "col2": "vec3"}},
            ],
        },
        "mat4": {
            "return": "mat4",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {
                    "params": {
                        "col0": "vec4",
                        "col1": "vec4",
                        "col3": "vec4",
                        "col3": "vec4",
                    }
                },
            ],
        },
        "sample": {
            "kind": "function",
            "return": "vec4",
            "overloads": [
                {"params": {"tex": "texture", "sample_position": "vec2"}},
                {"params": {"tex": "textureStack", "index": "int", "sample_position": "vec2"}},
            ],
        },
        "TIME": {
            "kind": "uniform",
            "type": "float"
        }
    },
    ShaderType.VERTEX: {
        "VERTEX_POSITION": {"type": "vec4", "kind": "output"},
        "VERTEX_INDEX": {"type": "int", "kind": "input"},
        # Was already implemented in the GL33 generator (lowers to
        # gl_InstanceID) but never actually declared as an FBUSL builtin, so
        # any shader referencing it would fail semantic analysis - invisible
        # only because semantic analysis was previously disabled.
        "INSTANCE_ID": {"type": "int", "kind": "variable"},
    },
    ShaderType.GEOMETRY: {
        # A geometry shader sets gl_Position once per EmitVertex() call, same
        # builtin as the vertex stage.
        "VERTEX_POSITION": {"type": "vec4", "kind": "output"},
        "EmitVertex": {"kind": "function", "return": None, "params": {}},
        "EndPrimitive": {"kind": "function", "return": None, "params": {}},
        # Reads the built-in per-input-vertex `gl_Position` at index `i`, for
        # `input=triangles`/etc. stages where `@input` fields arrive as
        # unsized arrays. A function rather than an indexable builtin
        # variable (there's nowhere else in FBUSL that models an indexable
        # builtin), which keeps this one geometry-only need out of the type
        # system.
        "input_position": {"kind": "function", "return": "vec4", "params": {"i": "int"}},
    },
    ShaderType.COMPUTE: {
        # Real GPU compute-invocation identity - the same on every backend
        # regardless of whether that backend has true hardware workgroups
        # (a capability-limited backend like GL33 still derives these
        # correctly via arithmetic, it just can't back them with real
        # co-scheduled/communicating invocations - see "compute.shared_memory"
        # and "compute.barrier" below).
        "GLOBAL_INVOCATION_ID": {"kind": "variable", "type": "ivec3"},
        "LOCAL_INVOCATION_ID": {"kind": "variable", "type": "ivec3"},
        "WORKGROUP_ID": {"kind": "variable", "type": "ivec3"},
        "NUM_WORKGROUPS": {"kind": "uniform", "type": "ivec3"},
        "DISPATCH_SIZE": {"kind": "uniform", "type": "ivec3"},
        # Requires actual co-scheduled, communicating invocations - a
        # fragment-shader-emulated backend (GL33) cannot support this.
        "barrier": {"kind": "function", "return": None, "params": {}, "requires": "compute.barrier"},
        "atomic_add": {"kind": "function", "return": "int", "params": {"target": "int", "value": "int"}, "requires": "compute.atomics"},
        "atomic_min": {"kind": "function", "return": "int", "params": {"target": "int", "value": "int"}, "requires": "compute.atomics"},
        "atomic_max": {"kind": "function", "return": "int", "params": {"target": "int", "value": "int"}, "requires": "compute.atomics"},
        "atomic_exchange": {"kind": "function", "return": "int", "params": {"target": "int", "value": "int"}, "requires": "compute.atomics"},
        "image_load": {"kind": "function", "return": "vec4", "params": {"img": "image", "coord": "ivec2"}, "requires": "compute.image_read"},
        "image_store": {"kind": "function", "return": None, "params": {"img": "image", "coord": "ivec2", "value": "vec4"}, "requires": "compute.image_write"},
    },
}

BUILTINS[ShaderType.RAYTRACE] = {
    # A raytrace shader is a compute shader that also gets ray-query
    # intrinsics - it runs through the exact same dispatch mechanism.
    **BUILTINS[ShaderType.COMPUTE],
    # Modeled as an *inline ray query* (single-shader-stage `trace_ray()`
    # call), not a raygen/closest-hit/any-hit/miss multi-stage pipeline with
    # a shader binding table - see the "Multi-backend design principle" in
    # the project plan for why: inline ray query is a real modern hardware
    # feature (VK_KHR_ray_query, DXR inline ray tracing) as well as the one
    # model a compute-emulated backend like GL33 can actually implement
    # (via software BVH traversal), unlike the classic pipeline model, which
    # has no GL33 equivalent at all.
    "make_ray": {"kind": "function", "return": "Ray", "params": {"origin": "vec3", "direction": "vec3"}},
    "ray_aabb": {"kind": "function", "return": "float", "params": {"ray": "Ray", "box_min": "vec3", "box_max": "vec3"}},
    "ray_triangle": {"kind": "function", "return": "vec4", "params": {"ray": "Ray", "v0": "vec3", "v1": "vec3", "v2": "vec3"}},
    "trace_ray": {"kind": "function", "return": "RayHit", "params": {"ray": "Ray"}, "requires": "raytrace.query"},
}

TYPES["Ray"] = {"fields": {"origin": "vec3", "direction": "vec3"}, "operations": {}}
TYPES["RayHit"] = {"fields": {"t": "float", "prim": "int", "u": "float", "v": "float", "hit": "bool"}, "operations": {}}
