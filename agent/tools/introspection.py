import importlib
import inspect
import sys
from typing import List, Dict, Any, Optional
from functools import lru_cache

from agent.schemas.api_cards import APICard

class IntrospectionTool:
    """
    Tool to introspect installed Python libraries and generate APICards.
    Ensures that the SimAgent only uses APIs that actually exist in the current environment.
    """

    _cache: Dict[str, APICard] = {}

    @classmethod
    def get_library_version(cls, library_name: str) -> str:
        """Get version of an installed library."""
        try:
            module = importlib.import_module(library_name)
            return getattr(module, '__version__', 'unknown')
        except ImportError:
            return 'not_installed'

    @classmethod
    def resolve_symbol(cls, symbol: str) -> Any:
        """
        Resolve a dot-path symbol to a Python object.
        e.g. 'pvlib.irradiance.get_total_irradiance' -> <function ...>
        """
        parts = symbol.split('.')
        if not parts:
            return None
        
        # Try to import strictly top-down
        # This is a heuristic: try to import the module part, then get attributes
        # e.g. pvlib.irradiance.get_total_irradiance
        # 1. import pvlib
        # 2. getattr(pvlib, irradiance) -> module
        # 3. getattr(module, get_total_irradiance) -> function
        
        # Find the longest prefix that is a module
        module = None
        module_name = ""
        remaining_parts = parts
        
        for i in range(len(parts), 0, -1):
            possible_module = '.'.join(parts[:i])
            try:
                module = importlib.import_module(possible_module)
                module_name = possible_module
                remaining_parts = parts[i:]
                break
            except ImportError:
                continue
        
        if module is None:
            # Try importing the root at least
            try:
                module = importlib.import_module(parts[0])
                module_name = parts[0]
                remaining_parts = parts[1:]
            except ImportError:
                return None

        # Traverse the remaining attributes
        obj = module
        for part in remaining_parts:
            try:
                obj = getattr(obj, part)
            except AttributeError:
                return None
        
        return obj

    @classmethod
    def introspect_symbol(cls, symbol: str) -> Optional[APICard]:
        """
        Generate an APICard for a given symbol.
        Uses caching to avoid repeated work.
        """
        if symbol in cls._cache:
            return cls._cache[symbol]

        obj = cls.resolve_symbol(symbol)
        if obj is None:
            return None

        # Determine library (assume first part of symbol)
        root_package = symbol.split('.')[0]
        version = cls.get_library_version(root_package)

        # Determine kind
        if inspect.isclass(obj):
            kind = 'class'
        elif inspect.ismethod(obj):
            kind = 'method'
        elif inspect.isfunction(obj):
            kind = 'function'
        else:
            # Maybe a constant or module? usage usually implies callable for APICards
            # We can support modules or constants if needed, but for now simplify
            return None 

        # Get signature
        try:
            sig = str(inspect.signature(obj))
        except (ValueError, TypeError):
            sig = "()" # Fallback for some builtins or C-extensions

        # Get docstring
        doc = inspect.getdoc(obj)
        short_doc = None
        if doc:
            # Take first non-empty block, max 3 lines
            lines = [line.strip() for line in doc.split('\n') if line.strip()]
            short_doc = '\n'.join(lines[:3])

        # Construct Import Stmt
        # Heuristic: from module import name
        # But symbol might be fully qualified.
        # e.g. pvlib.irradiance.get_total_irradiance
        # import_stmt = "from pvlib.irradiance import get_total_irradiance"
        # callable_name = "get_total_irradiance"
        
        # Improving import logic
        parts = symbol.split('.')
        mod_path = '.'.join(parts[:-1])
        name = parts[-1]
        
        if mod_path:
            import_stmt = f"from {mod_path} import {name}"
            callable_name = name
        else:
            # Top level function? Unlikely for library
            import_stmt = f"import {name}"
            callable_name = name

        card = APICard(
            symbol=symbol,
            import_stmt=import_stmt,
            callable_name=callable_name,
            kind=kind,
            signature=sig,
            doc=short_doc,
            version=version
        )
        
        cls._cache[symbol] = card
        return card

    @classmethod
    def introspect_many(cls, symbols: List[str]) -> List[APICard]:
        cards = []
        for s in symbols:
            card = cls.introspect_symbol(s)
            if card:
                cards.append(card)
        return cards
