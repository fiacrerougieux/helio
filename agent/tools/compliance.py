import ast
from typing import List, Dict, Set, Tuple
from agent.schemas.api_cards import APICard

class ComplianceResult:
    def __init__(self, allowed: bool, violations: List[str]):
        self.allowed = allowed
        self.violations = violations

def check_api_compliance(code: str, allowlist: List[APICard]) -> ComplianceResult:
    """
    Statically analyze code to ensure it only uses allowed APIs.
    
    Args:
        code: The Python code to check.
        allowlist: List of APICards defining allowed symbols.
        
    Returns:
        ComplianceResult with allowed status and list of violations.
    """
    
    # Base allowlist for non-pvlib essentials
    BASE_ALLOWLIST = {
        'pandas', 'numpy', 'json', 'math', 'datetime', 'time', 'typing', 'builtins',
        'print', 'len', 'range', 'enumerate', 'zip', 'list', 'dict', 'set', 'tuple', 'int', 'float', 'str', 'bool'
    }
    
    # Extract allowed symbols from cards
    # We allow the full symbol (pvlib.irradiance.get_total_irradiance)
    # AND the callable name if it's imported (get_total_irradiance)
    allowed_symbols = set()
    for card in allowlist:
        allowed_symbols.add(card.symbol)
        allowed_symbols.add(card.callable_name)
        # Also allow the parent module if it's part of the card
        # e.g. from pvlib import irradiance -> allowed: pvlib, irradiance
        parts = card.symbol.split('.')
        allowed_symbols.add(parts[0]) 

    # We also need to be careful about matching. 'pvlib.pvsystem' should be allowed if a function in it is allowed?
    # Actually, strict mode: if you use 'pvlib.pvsystem.pvwatts_dc', you must have the card for it.
    
    violations = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ComplianceResult(False, [f"Syntax Error: {e}"])

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                name = alias.name.split('.')[0]
                if name not in BASE_ALLOWLIST and name != 'pvlib':
                     # Allow logging or other agent utils? Maybe strict for now.
                     pass 
                # check pvlib imports?
                # For now we mainly care about usage, but imports matter too.
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module:
                mod_name = node.module.split('.')[0]
                if mod_name == 'pvlib':
                    # Check if the imported name is in cards
                    for alias in node.names:
                        full_name = f"{node.module}.{alias.name}"
                        # This is hard because 'from pvlib import irradiance' 
                        # just imports the module.
                        pass
            self.generic_visit(node)
            
        def visit_Attribute(self, node):
            # Check for pvlib.* usage
            # We try to reconstruct the full attribute chain e.g. pvlib.irradiance.get_total_irradiance
            chain = []
            curr = node
            while isinstance(curr, ast.Attribute):
                chain.append(curr.attr)
                curr = curr.value
            
            if isinstance(curr, ast.Name):
                chain.append(curr.id)
                full_name = ".".join(reversed(chain))
                
                # If it starts with pvlib, check it
                if full_name.startswith("pvlib."):
                     # Check exact match against allowed symbols
                     # But APICard symbol is the function, e.g. pvlib.irradiance.get_total_irradiance
                     # If code uses pvlib.irradiance.get_total_irradiance(args), that's fine.
                     # But if code uses pvlib.irradiance.some_other_func, that's a violation.
                     
                     # We only check leaf calls?
                     # Let's check if the full name (or prefixes) match known cards.
                     
                     # Actually, stricter: if it is a pvlib function, it MUST be in the allowlist.
                     # How do we know it's a function? We don't.
                     # We just verify that 'full_name' is either:
                     # 1. A prefix of an allowed card (e.g. pvlib.irradiance)
                     # 2. An exact allowed card
                     
                     is_prefix = False
                     is_exact = False
                     
                     for allowed in allowed_symbols:
                         if allowed == full_name:
                             is_exact = True
                         if allowed.startswith(full_name + "."):
                             is_prefix = True
                             
                     if not is_exact and not is_prefix:
                         # Potential violation provided it's not just an intermediate module
                         # For example: pvlib.irradiance might not be a "card" but it's a prefix.
                         # If it's NOT a prefix of any card, and NOT a card itself -> Violation.
                         violations.append(f"Forbidden usage: {full_name}")

            self.generic_visit(node)

    Visitor().visit(tree)
    
    return ComplianceResult(len(violations) == 0, violations)
