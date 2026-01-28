"""
Minimal RAG: Template schemas only (no full code examples).
"""
import json
from pathlib import Path


def load_templates():
    """Load minimal templates."""
    template_file = Path("rag/templates_minimal.json")
    if not template_file.exists():
        return []
    with open(template_file) as f:
        return json.load(f)


def get_relevant_template(query: str, task_type: str = None):
    """Get relevant template based on task type or query keywords."""
    templates = load_templates()

    if not templates:
        return None

    # Task type exact match (highest priority)
    if task_type:
        for tmpl in templates:
            if task_type in tmpl.get('task_types', []):
                return tmpl

    # Keyword matching
    query_lower = query.lower()
    for tmpl in templates:
        for tag in tmpl.get('tags', []):
            if tag in query_lower:
                return tmpl

    return None


def build_minimal_rag_prompt(query: str, task_type: str = None) -> str:
    """
    Build system prompt with minimal template injection.

    Args:
        query: User's query string
        task_type: Optional task type hint

    Returns:
        System prompt with template (if relevant)
    """
    from agent.prompts import SYSTEM_PROMPT

    # Get relevant template
    template = get_relevant_template(query, task_type)

    if not template:
        # No relevant template, use base prompt
        return SYSTEM_PROMPT

    # Inject template at the end of base prompt
    template_section = f"""

--- RELEVANT SCHEMA TEMPLATE ---

Task Type: {template['task_types'][0] if template.get('task_types') else 'N/A'}
Description: {template['description']}

Expected Schema:
{json.dumps(template['template'], indent=2)}

Guidance: {template.get('guidance', 'Follow the schema above')}

IMPORTANT: Return JSON action as usual: {{"action": "python", "code": "..."}}, then ensure your summary matches this schema.

---
"""

    return SYSTEM_PROMPT + template_section


if __name__ == "__main__":
    # Test
    test_queries = [
        ("Compare 30 vs 45 tilt", "comparison"),
        ("Annual energy for Sydney", "annual_yield"),
        ("Explain PVWatts", "explanation"),
    ]

    for query, task_type in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"Task: {task_type}")
        print(f"{'='*60}")

        prompt = build_minimal_rag_prompt(query, task_type)

        # Show template section only
        if "RELEVANT SCHEMA TEMPLATE" in prompt:
            template_start = prompt.index("RELEVANT SCHEMA TEMPLATE")
            print(prompt[template_start-10:template_start+500])
        else:
            print("No template matched")
