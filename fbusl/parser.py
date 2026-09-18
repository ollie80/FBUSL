from typing import List
import re
from fbusl import fbusl_error, Position
from typing import List, Optional
from enum import Enum, auto
from fbusl.node import *
import sys


class Token:
    def __init__(self, kind: str, value, pos: Position = Position()):
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.kind}, {repr(self.value)})"


class TokenType(Enum):
    INT = auto()
    BOOL = auto()
    ARROW = auto()
    IDENT = auto()
    FLOAT = auto()
    SYMBOL = auto()
    INDENT = auto()
    DEDENT = auto()
    NEWLINE = auto()
    KEYWORD = auto()
    COMMENT = auto()
    OPERATOR = auto()
    DECORATOR = auto()
    QUALIFIER = auto()
    WHITESPACE = auto()

TOKEN_TYPES = [
    (TokenType.NEWLINE, r"\n"), # newlines first
    (TokenType.WHITESPACE, r"[ \t]+"), # only spaces and tabs
    (TokenType.ARROW, r"->"),
    (TokenType.DECORATOR, r"@(?:uniform|input|output|define|compute|geometry|raytrace)"),
    # Word-boundary anchored: without `\b`, this matched the first 3-4
    # characters of any identifier merely *starting with* one of these
    # words (e.g. "median" -> QUALIFIER("med") + IDENT("ian"), "highlight"
    # -> QUALIFIER("high") + IDENT("light")) since regex matching isn't
    # anchored to whole tokens - only to a starting position.
    (TokenType.QUALIFIER, r"\b(low|med|flat|high)\b"),
    (TokenType.KEYWORD, r"\b(def|return|struct|if|buffer|elif|else|while|shared|readonly|writeonly|readwrite|not|and|or)\b"),
    (TokenType.BOOL, r"(True|False)"),
    (TokenType.IDENT, r"[a-zA-Z_][a-zA-Z0-9_]*"),
    (TokenType.FLOAT, r"\d(?:_?\d)*\.\d(?:_?\d)*"),
    (TokenType.INT, r"\d(?:_?\d)*"),
    (TokenType.SYMBOL, r"[{}()[\]:,\.]"),
    (TokenType.OPERATOR, r"(\+=|==|!=|<=|>=|-=|\*=|/=|=|\+|-|\*|/|<|>)"),
    (TokenType.COMMENT, r"#.*")
]


TOKEN_REGEX = [(kind, re.compile(pattern)) for kind, pattern in TOKEN_TYPES]

# Decorators that attach stage metadata to the `def` immediately following them
# (@compute/@geometry/@raytrace), as opposed to @uniform/@input/@output/@define
# which each introduce a block of standalone declarations.
STAGE_DECORATORS = {"@compute", "@geometry", "@raytrace"}


class Lexer:
    def __init__(self, code: str, filename: str = None):
        self.code = code
        self.filename = filename
        self.pos = 0 # absolute offset
        self.line = 1 # 1-based line number
        self.column = 0 # 0-based column within line
        self.length = len(code)
        self.indents = [0]
        self._pending_tokens: List[Token] = []

    def _make_position(self, start: int, end: int) -> Position:
        """Create a Position object for a token spanning [start:end]."""
        line = self.line
        col = self.column + (start - self.pos)
        return Position(line, self.filename, col, start, end)

    def next_token(self) -> Optional[Token]:
        if self._pending_tokens:
            return self._pending_tokens.pop(0)

        if self.pos >= self.length:
            if len(self.indents) > 1:
                self.indents.pop()
                return Token(
                    TokenType.DEDENT, "",
                    Position(self.line, self.filename, self.column, self.pos, self.pos)
                )
            return None

        ch = self.code[self.pos]

        if ch == "\n":
            self.pos += 1
            self.line += 1
            self.column = 0

            start_pos = self.pos
            while self.pos < self.length and self.code[self.pos] in " \t":
                self.pos += 1
                self.column += 1

            # Blank line or comment-only line: doesn't affect indentation tracking.
            next_ch = self.code[self.pos] if self.pos < self.length else ""
            if next_ch in ("\n", "#", ""):
                return self.next_token()

            indent = len(self.code[start_pos:self.pos].expandtabs())
            last_indent = self.indents[-1]

            if indent > last_indent:
                self.indents.append(indent)
                self._pending_tokens.append(
                    Token(TokenType.INDENT, "", Position(self.line, self.filename, self.column, self.pos, self.pos))
                )
            elif indent < last_indent:
                while len(self.indents) > 1 and indent < self.indents[-1]:
                    self.indents.pop()
                    self._pending_tokens.append(
                        Token(TokenType.DEDENT, "", Position(self.line, self.filename, self.column, self.pos, self.pos))
                    )

            return Token(
                TokenType.NEWLINE, "\n",
                Position(self.line - 1, self.filename, 0, self.pos - 1, self.pos)
            )

        if ch == "#":
            while self.pos < self.length and self.code[self.pos] != "\n":
                self.pos += 1
                self.column += 1
            return self.next_token()

        for kind, pattern in TOKEN_REGEX:
            match = pattern.match(self.code, self.pos)
            if match:
                value = match.group(0)
                start = self.pos
                end = match.end()
                tok_pos = Position(self.line, self.filename, self.column, start, end)

                self.pos = end
                self.column += len(value)

                if kind in (TokenType.WHITESPACE, TokenType.COMMENT):
                    return self.next_token()  # skip
                return Token(kind, value, tok_pos)

        fbusl_error(
            f"Unexpected character: {repr(str(self.code[self.pos]))}",
            Position(self.line, self.filename, self.column, self.pos, self.pos + 1),
        )
        self.pos += 1
        self.column += 1
        return self.next_token()

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.pos < self.length or self._pending_tokens:
            tok = self.next_token()
            if tok:
                tokens.append(tok)

        while len(self.indents) > 1:
            self.indents.pop()
            tokens.append(
                Token(TokenType.DEDENT, "", Position(self.line, self.filename, self.column, self.pos, self.pos))
            )

        return tokens

class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

        self.max_repeat_tokens = 5

    def peek(self) -> Token:
        """Return the current token without consuming it."""
        if self.position < len(self.tokens):
            return self.tokens[self.position]

        return Token("EOF", "", Position(self.position))

    def consume(self) -> Token:
        """Consume and return the current token."""
        tok = self.peek()
        self.position += 1
        return tok

    def expect(self, kind: str, value=None) -> Token:
        """
        Consume the current token if it matches the expected kind (and optionally value),
        otherwise raise an error.
        """
        tok = self.peek()
        if tok.kind != kind or (value is not None and tok.value != value):
            msg = f"Expected token {kind}"
            if value is not None:
                msg += f" with value {value}"
            msg += f', but got {tok.kind} ("{tok.value}")'
            fbusl_error(msg, self.get_current_pos())
        self.position += 1
        return tok

    def get_current_pos(self) -> Position:
        """Return the Position object of the current token."""
        tok = self.peek()
        return tok.pos

    def parse(self):
        ast: list[ASTNode] = []
        stall_count = 0

        while self.position < len(self.tokens):
            # Guards against a genuine parser bug (parse_next() returning a
            # node without actually consuming any tokens, which would spin
            # forever since the loop condition never changes) - keyed off
            # whether `self.position` itself advanced, not off the *kind* of
            # token each top-level node happened to start with. That
            # previous approach mistook any 5 consecutive top-level
            # declarations of the same kind (5 `def`s, 5 `buffer`s, ...) -
            # completely ordinary in a real shader with several helper
            # functions - for an infinite loop and aborted compilation.
            pos_before = self.position
            token = self.peek()
            node = self.parse_next()

            if node is None:
                self.consume()
                continue

            if isinstance(node, list):
                ast.extend(node)
            else:
                ast.append(node)

            if self.position == pos_before:
                stall_count += 1
                if stall_count >= self.max_repeat_tokens:
                    fbusl_error(
                        f"Parser made no progress at token: {token}", self.get_current_pos()
                    )
            else:
                stall_count = 0

        return ast

    def parse_next(self):
        token = self.peek()

        if token.kind == TokenType.DECORATOR:
            return self.parse_decorator()

        if token.kind == TokenType.KEYWORD:
            if token.value == "def":
                return self.parse_function_def()
            if token.value == "struct":
                return self.parse_struct_def()
            if token.value in {"if", "else", 'elif'}:
                return self.parse_if_statement()
            if token.value == "while":
                return self.parse_while_statement()
            if token.value in {"buffer", "readonly", "writeonly", "readwrite"}:
                return self.parse_buffer_def()
            if token.value == "shared":
                return self.parse_shared_decl()
            if token.value == "return":
                return self.parse_return_statement()

        if token.kind == TokenType.IDENT:
            return self.parse_identifier()

    def parse_if_statement(self):
        pos = self.get_current_pos()
        kw = self.expect(TokenType.KEYWORD).value

        condition = None

        if kw in {"if", "elif"}:

            if self.peek().value == "(":
                self.consume()
                condition = self.parse_expression()
                self.expect(TokenType.SYMBOL, ")")
            else:
                condition = self.parse_expression()

        self.expect(TokenType.SYMBOL, ":")
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        body = []
        while self.peek().kind != TokenType.DEDENT:
            #
            # parse_next() returns None (without consuming anything)
            # for any token it doesn't recognize as the start of a
            # statement - including the synthetic "EOF" token peek()
            # returns once the token stream runs out. Without the
            # consume()-on-None guard below, hitting one of those
            # tokens here just re-parses the same token forever:
            # self.position never advances, parse_next() never raises
            # an error for an "unhandled" (as opposed to genuinely
            # invalid) token, so this hangs with no output at all.
            # parse_function_def's body loop already guards against
            # this - this loop needs the same guard.
            #
            node = self.parse_next()
            if node is None:
                self.consume()
                continue

            body.append(node)

            if self.peek().kind == TokenType.NEWLINE:
                self.consume()

        self.expect(TokenType.DEDENT)

        next_clause = None
        if self.peek().kind == TokenType.KEYWORD and self.peek().value in {"elif", "else"}:
            next_clause = self.parse_if_statement()

        return IfStatement(condition, kw, body, next_clause, pos)

    def parse_while_statement(self) -> WhileStatement:
        pos = self.get_current_pos()
        self.expect(TokenType.KEYWORD, "while")

        if self.peek().value == "(":
            self.consume()
            condition = self.parse_expression()
            self.expect(TokenType.SYMBOL, ")")
        else:
            condition = self.parse_expression()

        self.expect(TokenType.SYMBOL, ":")
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        body = []
        while self.peek().kind != TokenType.DEDENT:
            node = self.parse_next()
            if node is None:
                self.consume()
                continue

            body.append(node)

            if self.peek().kind == TokenType.NEWLINE:
                self.consume()

        self.expect(TokenType.DEDENT)

        return WhileStatement(condition, body, pos)

    def parse_inline_if(self):
        then_expr = self.parse_expression()

        if self.peek().kind == TokenType.KEYWORD and self.peek().value == "if":
            self.consume()
            condition = self.parse_expression()

            if self.peek().kind != TokenType.KEYWORD or self.peek().value != "else":
                fbusl_error("Expected 'else' in inline if expression", self.get_current_pos())
            self.consume()

            else_expr = self.parse_expression()

            return InlineIf(then_expr, condition, else_expr)

        return then_expr

    def parse_type(self) -> dict:
        name = self.expect(TokenType.IDENT).value

        if self.peek().value == "[":

            self.expect(TokenType.SYMBOL, "[")
            length = self.expect(TokenType.INT).value
            self.expect(TokenType.SYMBOL, "]")

            return {"name": "array", "data": {"length": length, "base_type": name}}
        
        else:
            return {"name": name}

    def parse_function_def(self) -> FunctionDef:
        position = self.get_current_pos()
        self.expect(TokenType.KEYWORD, "def")

        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.SYMBOL, "(")

        params = []

        first = True
        while self.peek().value != ")":
            if not first:
                self.expect(TokenType.SYMBOL, ",")

            param_name = self.expect(TokenType.IDENT).value
            param_type, param_qualifier = self.parse_type_and_qualifier()

            if param_qualifier not in ["in", "inout", "out", None]:
                fbusl_error(
                    'Function parameters can only have qualifiers of "in", "out", and "inout".',
                    position,
                )

            params.append(
                FunctionParam(param_name, param_type, param_qualifier, position)
            )

            first = False
        
        self.expect(TokenType.SYMBOL, ")")

        return_type = None
        if self.peek().kind == TokenType.ARROW:
            self.expect(TokenType.ARROW)
            return_type = self.parse_type()

        self.expect(TokenType.SYMBOL, ":")
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        body = []

        while self.peek().kind != TokenType.DEDENT:
            node = self.parse_next()
            if node is None:
                self.consume()  # skip unknown or blank token
                continue

            if isinstance(node, list):
                body.extend(node)
            else:
                body.append(node)

            if self.peek().kind == TokenType.NEWLINE:
                self.consume()

        self.expect(TokenType.DEDENT)

        return FunctionDef(name, body, return_type, params)

    def parse_struct_def(self) -> StructDef:
        position = self.get_current_pos()

        self.expect(TokenType.KEYWORD, 'struct')
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.SYMBOL, ':')
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        fields = []
        while self.peek().kind != TokenType.DEDENT:
            field_position = self.get_current_pos()
            field_name = self.expect(TokenType.IDENT).value
            field_type, field_precision = self.parse_type_and_qualifier()

            fields.append(StructField(field_name, field_type, field_position))  

            self.expect(TokenType.NEWLINE)

        self.expect(TokenType.DEDENT)

        return StructDef(name, fields, position)

    def parse_buffer_def(self) -> BufferBlock:
        position = self.get_current_pos()

        qualifier = "readonly"
        if self.peek().kind == TokenType.KEYWORD and self.peek().value in ("readonly", "writeonly", "readwrite"):
            qualifier = self.consume().value

        self.expect(TokenType.KEYWORD, 'buffer')
        name = self.expect(TokenType.IDENT).value
        self.expect(TokenType.SYMBOL, ':')
        self.expect(TokenType.NEWLINE)
        self.expect(TokenType.INDENT)

        fields = []
        while self.peek().kind != TokenType.DEDENT:
            field_position = self.get_current_pos()
            field_name = self.expect(TokenType.IDENT).value
            field_type, _ = self.parse_type_and_qualifier()

            fields.append(BufferField(field_name, field_type, field_position))

            self.expect(TokenType.NEWLINE)

        self.expect(TokenType.DEDENT)

        return BufferBlock(name, fields, qualifier, position)

    def parse_shared_decl(self) -> SharedDecl:
        position = self.get_current_pos()
        self.expect(TokenType.KEYWORD, 'shared')
        name = self.expect(TokenType.IDENT).value
        var_type, _ = self.parse_type_and_qualifier()
        return SharedDecl(name, var_type, position)

    def parse_return_statement(self) -> Return:
        position = self.get_current_pos()
        self.expect(TokenType.KEYWORD, 'return')

        expression = None
        if self.peek().kind != TokenType.NEWLINE:
            expression = self.parse_expression()

        return Return(expression, position)

    def parse_decorator(self) -> ASTNode:
        decorator_type = self.expect(TokenType.DECORATOR).value

        if decorator_type in STAGE_DECORATORS:
            return self.parse_stage_decorator(decorator_type)

        self.expect(TokenType.NEWLINE)

        decorators = []

        while self.peek().kind == TokenType.IDENT:
            position = self.get_current_pos()
            if decorator_type in ["@uniform", "@input", "@output"]:

                name = self.expect(TokenType.IDENT).value
                var_type, qualifier = self.parse_type_and_qualifier()

                dec_class_map = {
                    "@output": Output,
                    "@input": Input,
                    "@uniform": Uniform,
                }
                decorators.append(
                    dec_class_map[decorator_type](name, var_type, qualifier, position)
                )

            else:
                name = self.expect(TokenType.IDENT).value

                self.expect(TokenType.OPERATOR, "=")

                val = self.parse_expression()

                decorators.append(Define(name, val, position))

            self.expect(TokenType.NEWLINE)

        return decorators

    def parse_stage_decorator(self, decorator_type: str) -> FunctionDef:
        """Parses `@compute(...)`/`@geometry(...)`/`@raytrace(...)`, an optional
        `(key=value, ...)` argument list immediately followed by the `def` it
        decorates. Returns that `FunctionDef` with `.stage`/`.stage_args` set,
        rather than a list of standalone declarations like the other decorators
        - `Parser.parse()` already accepts either shape from `parse_next()`.
        """
        args: dict = {}

        if self.peek().kind == TokenType.SYMBOL and self.peek().value == "(":
            self.consume()

            while self.peek().value != ")":
                key = self.expect(TokenType.IDENT).value
                self.expect(TokenType.OPERATOR, "=")

                if self.peek().kind == TokenType.IDENT:
                    value = self.consume().value
                else:
                    value = self.parse_literal().value

                args[key] = value

                if self.peek().kind == TokenType.SYMBOL and self.peek().value == ",":
                    self.consume()

            self.expect(TokenType.SYMBOL, ")")

        self.expect(TokenType.NEWLINE)

        if not (self.peek().kind == TokenType.KEYWORD and self.peek().value == "def"):
            fbusl_error(
                f"'{decorator_type}' must directly precede a function definition",
                self.get_current_pos(),
            )

        func = self.parse_function_def()
        func.stage = decorator_type[1:]
        func.stage_args = args
        return func

    def parse_type_and_qualifier(self) -> tuple[dict, str | None]:
        self.expect(TokenType.SYMBOL, ":")

        prec = None
        if self.peek().kind == TokenType.QUALIFIER:
            prec = self.expect(TokenType.QUALIFIER).value

        node_type = self.parse_type()

        return node_type, prec

    def parse_identifier(self) -> ASTNode:
        node = Identifier(self.consume().value, pos=self.get_current_pos())

        while True:
            tok = self.peek()

            if tok.kind == TokenType.SYMBOL and tok.value == ".":
                self.consume()
                member_tok = self.expect(TokenType.IDENT)
                node = MemberAccess(node, member_tok.value, pos=member_tok.pos)

            elif tok.kind == TokenType.SYMBOL and tok.value == "[":
                self.consume()
                index_expr = self.parse_expression()
                self.expect(TokenType.SYMBOL, "]")
                node = ArrayAccess(node, index_expr, pos=self.get_current_pos())

            elif tok.kind == TokenType.SYMBOL and tok.value == "(":
                self.consume()
                args = self.parse_call_args()
                self.expect(TokenType.SYMBOL, ")")
                node = FuncCall(node.value, args, pos=self.get_current_pos())

            elif tok.kind == TokenType.OPERATOR and tok.value == "=":
                self.consume()
                expr = self.parse_expression()
                node = Setter(node, expr, self.get_current_pos())

            elif tok.kind == TokenType.SYMBOL and tok.value == ":":
                return self.parse_var_decl(node.value)

            else:
                break

        return node

    def parse_var_decl(self, name=None) -> ASTNode:
        pos = self.get_current_pos()

        if name == None:
            name = self.expect(TokenType.IDENT).value

        node_type, qualifier = self.parse_type_and_qualifier()

        value = None
        if self.peek().kind == TokenType.OPERATOR and self.peek().value == "=":
            self.consume()
            value = self.parse_expression()

        return VarDecl(
            name=name, var_type=node_type, value=value, qualifier=qualifier, pos=pos
        )

    def parse_literal(self) -> ASTNode:
        tok = self.consume()
        if tok.kind == TokenType.INT:
            return Literal(int(tok.value), pos=tok.pos)
        elif tok.kind == TokenType.FLOAT:
            return Literal(float(tok.value), pos=tok.pos)
        elif tok.kind == TokenType.BOOL and tok.value in ["True", "False"]:
            return Literal(tok.value == "True", pos=tok.pos)
        else:
            fbusl_error(f"Invalid literal: {tok.value}", tok.pos)

    def parse_identifier_expr(self) -> ASTNode:
        node = Identifier(self.consume().value)

        while True:
            tok = self.peek()

            if tok.kind == TokenType.SYMBOL and tok.value == ".":
                self.consume()
                member_tok = self.expect(TokenType.IDENT)
                node = MemberAccess(node, member_tok.value)

            elif tok.kind == TokenType.SYMBOL and tok.value == "[":
                self.consume()
                index_expr = self.parse_expression()
                self.expect(TokenType.SYMBOL, "]")
                node = ArrayAccess(node, index_expr)

            elif tok.kind == TokenType.SYMBOL and tok.value == "(":
                self.consume()
                args = self.parse_call_args()
                self.expect(TokenType.SYMBOL, ")")
                node = FuncCall(node, args)

            else:
                break

        return node

    def parse_call_args(self) -> List[ASTNode]:
        args = []
        tok = self.peek()
        if tok.kind == TokenType.SYMBOL and tok.value == ")":
            return args

        while True:
            arg = self.parse_expression()
            args.append(arg)
            tok = self.peek()
            if tok.kind == TokenType.SYMBOL and tok.value == ",":
                self.consume()
            else:
                break
        return args

    def parse_expression(self, precedence=0) -> ASTNode:
        left = self.parse_unary()

        if self.peek().kind == TokenType.KEYWORD and self.peek().value == "if":
            self.consume()
            condition = self.parse_expression()

            if self.peek().kind != TokenType.KEYWORD or self.peek().value != "else":
                fbusl_error("Expected 'else' in inline if expression", self.get_current_pos())
            self.consume()

            else_expr = self.parse_expression()
            return InlineIf(left, condition, else_expr)

        while True:
            tok = self.peek()
            if tok.kind != TokenType.OPERATOR:
                break

            op = tok.value
            op_prec = self.get_operator_precedence(op)
            if op_prec < precedence:
                break

            self.consume()
            right = self.parse_expression(op_prec + 1)
            left = BinOp(left, op, right)

        return left


    def parse_unary(self) -> ASTNode:
        tok = self.peek()
        if tok.kind == TokenType.OPERATOR and tok.value in ("+", "-", "not"):
            op = self.consume().value
            operand = self.parse_unary()
            return UnaryOp(op, operand, pos=tok.pos)
        else:
            return self.parse_primary()

    def parse_primary(self) -> ASTNode:
        tok = self.peek()

        if tok.kind == TokenType.IDENT:
            return self.parse_identifier()

        elif tok.kind in (TokenType.INT, TokenType.FLOAT, TokenType.BOOL):
            return self.parse_literal()

        elif tok.kind == TokenType.SYMBOL and tok.value == "(":
            self.consume()
            expr = self.parse_expression()
            self.expect(TokenType.SYMBOL, ")")
            return expr

        else:
            fbusl_error(
                f"Unexpected token in expression: {tok.kind} ({tok.value})", tok.pos
            )

    def get_operator_precedence(self, op: str) -> int:
        PRECEDENCE = {
            "*": 10,
            "/": 10,
            "%": 10,
            "+": 9,
            "-": 9,
            "<<": 8,
            ">>": 8,
            "<": 7,
            "<=": 7,
            ">": 7,
            ">=": 7,
            "==": 6,
            "!=": 6,
            "&": 5,
            "^": 4,
            "|": 3,
            "and": 2,
            "or": 1,
            "=": 0,
        }
        return PRECEDENCE.get(op, -1)
