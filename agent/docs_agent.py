from typing import List, Dict, Any
from agent.tools.introspection import IntrospectionTool
from agent.schemas.api_cards import APICard

class DocsAgent:
    """
    The Librarian.
    Responsibilities:
    1. Receive a list of needed API symbols.
    2. Retrieve APICards via introspection (runtime verification).
    3. (Future) Supplement with local documentation RAG.
    """

    def __init__(self):
        self.introspection_tool = IntrospectionTool()

    def retrieve_cards(self, symbols: List[str]) -> List[APICard]:
        """
        Retrieve API cards for the requested symbols.
        """
        if not symbols:
            return []
            
        return self.introspection_tool.introspect_many(symbols)

    def retrieve_cards_as_json(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Returns serialized APICards for the SimAgent.
        """
        cards = self.retrieve_cards(symbols)
        return [card.model_dump() for card in cards]
