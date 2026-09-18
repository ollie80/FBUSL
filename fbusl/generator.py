from fbusl.node import ASTNode
from fbusl import fbusl_error, Position, ShaderType


class Generator:
    """Base class for FBUSL code generators (one subclass per graphics backend).

    A backend declares what it actually supports via `CAPABILITIES` - a set of
    capability strings such as "compute.dispatch", "compute.shared_memory",
    "compute.barrier", "compute.atomics", "compute.buffer_write",
    "compute.image_write", "geometry.native", "raytrace.query_hardware",
    "raytrace.query_emulated". FBUSL's language/AST/builtins are backend-agnostic
    and always allow every construct; it is the generator's job to reject, with a
    clear error, any construct whose required capability isn't in this set,
    rather than silently mis-lowering it. This is what lets the same shader
    source target a fully-capable backend (e.g. a future native-compute GL4.4/
    Vulkan/Metal backend) and a deliberately limited one (e.g. GL33's
    fragment-shader-emulated compute) without the language itself shrinking to
    the lowest common denominator.
    """

    CAPABILITIES: frozenset[str] = frozenset()

    def __init__(self, tree: list[ASTNode], shader_type: ShaderType):
        self.tree = tree
        self.shader_type = shader_type

    def has_capability(self, capability: str) -> bool:
        if capability == "raytrace.query":
            return (
                "raytrace.query_hardware" in self.CAPABILITIES
                or "raytrace.query_emulated" in self.CAPABILITIES
            )
        return capability in self.CAPABILITIES

    def require(self, capability: str, what: str, pos: Position = Position()):
        """Raises a clear fbusl_error if `capability` isn't supported by this backend."""
        if not self.has_capability(capability):
            fbusl_error(
                f"'{what}' requires capability '{capability}', which is not "
                f"supported by the {self.__class__.__name__} backend.",
                pos,
            )

    def generate(self) -> str:
        return ""
