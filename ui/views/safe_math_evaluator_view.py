import ast
import operator


class SafeMathEvaluator:
    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    @classmethod
    def evaluate(cls, expression: str) -> float:
        try:
            # Handle plain numbers first (simple optimization)
            if expression.isdigit() or (len(expression) > 1 and expression[0] in '+-' and expression[1:].isdigit()):
                return int(expression)
            
            tree = ast.parse(expression, mode="eval")
            return cls._eval_node(tree.body)
        except (ValueError, SyntaxError) as e:
            raise ValueError(f"Invalid expression: {e}")
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}")
    
    @classmethod
    def _eval_node(cls, node):
        # Handle ast.Constant (Python 3.8+)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Invalid constant")
        
        # Handle ast.Num for backward compatibility (Python < 3.8)
        if hasattr(ast, 'Num') and isinstance(node, ast.Num):
            if isinstance(node.n, (int, float)):
                return node.n
            raise ValueError("Invalid constant")
        
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError("Operator not allowed")
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            return cls.ALLOWED_OPERATORS[op_type](left, right)
        
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError("Unary operator not allowed")
            operand = cls._eval_node(node.operand)
            return cls.ALLOWED_OPERATORS[op_type](operand)
        
        raise ValueError(f"Invalid expression structure: {type(node).__name__}")
