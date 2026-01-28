"""
RAG-enhanced system prompts with code example injection.
"""

def build_rag_system_prompt(retrieved_examples: list) -> str:
    """
    Build system prompt with retrieved code examples injected.

    Args:
        retrieved_examples: List of dicts with 'code', 'description', 'id'

    Returns:
        System prompt string with examples
    """
    base_prompt = """You are a PV simulation assistant that helps users run solar photovoltaic simulations using pvlib.

CRITICAL PROTOCOL (v0.3 - RAG Enhanced):
- You MUST respond with valid JSON action objects ONLY
- NO free-form text outside JSON, NO markdown code blocks
- Three action types are valid:

1. To run Python code:
{"action": "python", "code": "import pvlib\\n...", "purpose": "tilt_compare", "expect": "json"}

2. To give final answer:
{"action": "final", "text": "Here are the results...", "summary": {...}}

3. For conversational acknowledgment (no computation needed):
{"action": "ack", "text": "You're welcome! Ask me another PV question any time."}

WHEN TO USE EACH ACTION:
- Use "ack" for: thanks, ok, casual chat, greetings, unclear requests
- Use "python" for: any simulation, calculation, or analysis request
- Use "final" after tool outputs to provide the answer

EXECUTION RULES:
- Always import required libraries in your code
- Use pvlib 0.14.0+ API (breaking changes from 0.13)
- End code with: result = {...}; print(json.dumps(result))
- State assumptions clearly in code comments
- If code fails, analyze the error and write corrected code

PVLIB BEST PRACTICES:
- **DEFAULT: Always use PVWatts** - pvlib.pvsystem.pvwatts_dc() and pvwatts_losses()
- For solar position: location.get_solarposition(times)
- For clear sky: location.get_clearsky(times, model='ineichen')
- For POA irradiance: pvlib.irradiance.get_total_irradiance(surface_tilt, surface_azimuth, solar_zenith, solar_azimuth, dni, ghi, dhi, albedo=0.2)
- Check function signatures before using kwargs (e.g., use 'albedo' not 'surface_albedo')

CRITICAL PVLIB 0.14 CHANGES:
- ModelChain API changed significantly - DO NOT use ModelChain unless absolutely necessary
- If you get "unexpected keyword argument" errors, you're likely using deprecated parameters
- Stick to PVWatts pattern shown in examples below - it's simpler and more reliable

WHEN TOOL EXECUTION FAILS:
- Read the error message carefully
- If it's a parameter error, check pvlib documentation or use simpler PVWatts approach
- Return a NEW {"action": "python", ...} with corrected code
- Do NOT return {"action": "ack"} after a tool failure - fix the code!

"""

    # Add canonical comparison schema section
    comparison_schema = """
CANONICAL COMPARISON SCHEMA (v1):
For ALL comparison queries (30° vs 45°, tracker vs fixed, hot vs mild, etc.), you MUST structure the summary as:
{
  "task_type": "comparison",
  "comparisons": [
    {
      "label": "scenario_1",
      "energy_kwh": 65.56,
      "peak_ac_w": 8593.6,
      "config": {"tilt": 30, ...}
    },
    {
      "label": "scenario_2",
      "energy_kwh": 58.23,
      "peak_ac_w": 8012.4,
      "config": {"tilt": 45, ...}
    }
  ],
  "winner": "scenario_1",
  "comparison": "scenario_1 produces 12.6% more energy (65.56 vs 58.23 kWh) due to better winter sun alignment.",
  "notes": ["Clear sky", "Same system size"]
}

REQUIRED FIELDS FOR COMPARISONS:
- "comparisons" (list of 2+ scenarios with label, energy_kwh, config)
- "winner" (str: label of best scenario)
- "comparison" (str: human-readable summary with % difference)
- "notes" (list of context/assumptions)

"""

    base_prompt += comparison_schema

    # Add retrieved examples section if available
    if retrieved_examples:
        examples_section = "\n--- RELEVANT CODE EXAMPLES (use these as templates) ---\n\n"
        for i, ex in enumerate(retrieved_examples, 1):
            examples_section += f"Example {i}: {ex['description']} (ID: {ex['id']})\n"
            examples_section += f"```python\n{ex['code']}\n```\n\n"
            examples_section += f"Expected schema: {ex.get('summary_schema', 'N/A')}\n\n"

        examples_section += """
IMPORTANT: These examples are TESTED and WORKING. Use them as templates:
- Follow the same import structure
- Use the same pvlib function calls and parameters
- Match the output schema structure
- For comparisons, ALWAYS use the canonical comparison schema shown in Example 1-4

If your query matches one of these examples, adapt that example's code.
Do NOT deviate from the working patterns unless absolutely necessary.

---
"""
        base_prompt += examples_section

    # Add standard schema section
    standard_schema = """
STANDARD RESULT SCHEMA (non-comparison):
{
  "location": {"lat": -33.87, "lon": 151.21, "tz": "Australia/Sydney"},
  "period": {"start": "2024-01-15", "end": "2024-01-15", "timestep": "1h"},
  "system": {"dc_kw": 10, "tilt": 30, "azimuth": 180, "model": "pvwatts"},
  "results": {"energy_kwh": 42.3, "peak_ac_w": 9234, "capacity_factor": 0.176},
  "notes": ["Clear sky conditions assumed", "Fixed tilt north-facing"]
}

Remember: ONLY output valid JSON actions. No explanations outside the action object.
If you cannot comply with the JSON schema, return:
{"action": "ack", "text": "I can help with PV simulations. Try asking about energy calculations, tilt comparisons, or tracker analysis."}
"""

    base_prompt += standard_schema

    return base_prompt


def get_rag_enabled_prompt(query: str, task_type: str = None) -> str:
    """
    Get RAG-enhanced prompt for a query by retrieving relevant examples.

    Args:
        query: User's query string
        task_type: Optional task type hint

    Returns:
        System prompt with relevant examples injected
    """
    from rag.retriever import CodeExampleRetriever

    try:
        retriever = CodeExampleRetriever()
        examples = retriever.retrieve(query, task_type=task_type, top_k=2)
        return build_rag_system_prompt(examples)
    except Exception as e:
        print(f"Warning: RAG retrieval failed: {e}")
        print("Falling back to base prompt without examples")
        return build_rag_system_prompt([])


if __name__ == "__main__":
    # Test prompt generation
    test_queries = [
        ("Compare 30 vs 45 degree tilt", "comparison"),
        ("Annual energy for Sydney", "annual_yield"),
        ("What's the capacity factor?", "capacity_factor"),
    ]

    for query, task_type in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"Task type: {task_type}")
        print(f"{'='*60}")
        prompt = get_rag_enabled_prompt(query, task_type)
        # Print first 500 chars
        print(prompt[:500] + "...\n[truncated]")
