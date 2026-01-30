import ast
import textwrap
from typing import List, Dict, Set, Tuple, Optional
from agent.schemas.api_cards import APICard

class ComplianceResult:
    def __init__(self, allowed: bool, violations: List[str], repaired_code: Optional[str] = None):
        self.allowed = allowed
        self.violations = violations
        self.repaired_code = repaired_code  # Non-None if syntax was auto-repaired


def attempt_syntax_repair(code: str) -> Optional[str]:
    """
    Attempt to auto-repair common syntax issues in generated code.

    Tries these strategies in order:
    1. textwrap.dedent (fixes uniform extra indentation)
    2. Strip leading whitespace from first non-import line
       (fixes 'unexpected indent' from LLM artifacts)
    3. Remove blank/whitespace-only lines that break indentation

    Returns:
        Repaired code string if repair succeeded (parses cleanly), None otherwise.
    """
    # Strategy 1: dedent the whole block
    dedented = textwrap.dedent(code)
    try:
        ast.parse(dedented)
        return dedented
    except SyntaxError:
        pass

    # Strategy 2: find the offending line and try to fix its indentation
    lines = code.split('\n')
    # Try parsing incrementally to find the bad line
    try:
        ast.parse(code)
        return code  # Already valid
    except SyntaxError as e:
        if e.lineno is not None and 1 <= e.lineno <= len(lines):
            bad_idx = e.lineno - 1
            bad_line = lines[bad_idx]
            stripped = bad_line.lstrip()
            if stripped:
                # Try stripping all leading whitespace from the bad line
                fixed_lines = lines.copy()
                # Determine expected indent from previous non-empty line
                expected_indent = ""
                for i in range(bad_idx - 1, -1, -1):
                    prev = lines[i]
                    if prev.strip():
                        expected_indent = prev[:len(prev) - len(prev.lstrip())]
                        # If previous line ends with ':', add one indent level
                        if prev.rstrip().endswith(':'):
                            expected_indent += "    "
                        break

                fixed_lines[bad_idx] = expected_indent + stripped
                fixed_code = '\n'.join(fixed_lines)
                try:
                    ast.parse(fixed_code)
                    return fixed_code
                except SyntaxError:
                    pass

    # Strategy 3: remove trailing whitespace and blank lines between statements
    cleaned = '\n'.join(line.rstrip() for line in lines)
    try:
        ast.parse(cleaned)
        return cleaned
    except SyntaxError:
        pass

    return None


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
    syntax_was_repaired = False

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        # Attempt auto-repair before failing
        repaired = attempt_syntax_repair(code)
        if repaired is not None:
            try:
                tree = ast.parse(repaired)
                # Repair succeeded - continue compliance check with repaired code
                code = repaired
                syntax_was_repaired = True
            except SyntaxError:
                return ComplianceResult(False, [f"Syntax Error: {e}"])
        else:
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
                         #
                         # Provide targeted feedback for data ingestion modules
                         if full_name.startswith("pvlib.iotools"):
                             violations.append(
                                 f"Forbidden usage: {full_name} "
                                 "(data ingestion APIs require explicit APICard approval; "
                                 "use clearsky or pre-loaded weather data instead)"
                             )
                         else:
                             violations.append(f"Forbidden usage: {full_name}")

            self.generic_visit(node)

    Visitor().visit(tree)

    repaired_code = code if syntax_was_repaired else None
    return ComplianceResult(len(violations) == 0, violations, repaired_code=repaired_code)
