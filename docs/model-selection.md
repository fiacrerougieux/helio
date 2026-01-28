# Model Selection Guide

## Default Model

**Current default**: `openai/gpt-4o-mini`

This was chosen for:
- ✅ **Stability** - Excellent reliability, fewer intermittent errors
- ✅ **Speed** - Very fast response times (~800 tokens/sec)
- ✅ **Large context** - 128K token context window
- ✅ **Quality** - Production-grade code generation
- ✅ **Cost-effective** - ~$0.15 per 1M input tokens

## Supported Models

### Recommended Models

| Model | Cost (per 1M tokens) | Speed | Context | Best For |
|-------|---------------------|-------|---------|----------|
| **openai/gpt-4o-mini** | $0.15 in / $0.60 out | Very Fast | 128K | **Default - Best balance** |
| openai/gpt-4o | $2.50 in / $10 out | Fast | 128K | Complex queries, highest quality |
| qwen/qwen-2.5-coder-32b-instruct | $0.14 in / $0.14 out | Fast | 32K | Code-specialized, budget option |
| anthropic/claude-3.5-sonnet | $3.00 in / $15 out | Fast | 200K | Highest quality, large context |

### Budget Models

| Model | Cost (per 1M tokens) | Notes |
|-------|---------------------|-------|
| qwen/qwq-32b-preview | $0.14 in / $0.14 out | Reasoning-focused |
| google/gemini-flash-1.5 | $0.075 in / $0.30 out | Very fast, cheap |
| meta-llama/llama-3.1-70b-instruct | $0.50 in / $0.75 out | Open source, good quality |

## Switching Models

### Temporary (One Session)

```cmd
python -m agent.multi_agent_cli --model openai/gpt-4o
```

### Change Default

Edit `agent/multi_agent_cli.py`:

```python
def __init__(
    self,
    model: str = "openai/gpt-4o-mini",  # ← Change this line
    ...
):
```

Or edit the `main()` function:

```python
parser.add_argument("--model", default="openai/gpt-4o-mini", ...)  # ← Change this
```

## Cost Estimates

### Typical Session (5-10 queries)

**Input** (prompts + code):
- Per query: ~2,000-5,000 tokens
- Session total: ~10,000-50,000 tokens

**Output** (generated code + responses):
- Per query: ~500-2,000 tokens
- Session total: ~2,500-20,000 tokens

**Cost per session**:
- **GPT-4o-mini**: $0.002-0.02 (~2 cents)
- **Qwen 2.5 Coder**: $0.001-0.01 (~1 cent)
- **GPT-4o**: $0.025-0.50 (~25-50 cents)
- **Claude 3.5 Sonnet**: $0.03-0.75 (~30-75 cents)

### Daily Usage (50 queries)

| Model | Daily Cost | Monthly Cost |
|-------|-----------|--------------|
| **GPT-4o-mini** | $0.10 | $3.00 |
| Qwen 2.5 Coder | $0.05 | $1.50 |
| GPT-4o | $2.50 | $75.00 |
| Claude 3.5 Sonnet | $3.00 | $90.00 |

## Performance Comparison

### Code Quality

1. **Claude 3.5 Sonnet** - Best overall (complex reasoning)
2. **GPT-4o** - Excellent (production-grade)
3. **GPT-4o-mini** - Excellent (fast, reliable)
4. **Qwen 2.5 Coder 32B** - Very good (code-specialized)

### Speed (Response Time)

1. **GPT-4o-mini** - Fastest (~800 tok/s)
2. **Gemini Flash 1.5** - Very fast (~700 tok/s)
3. **Qwen 2.5 Coder** - Fast (~500 tok/s)
4. **GPT-4o** - Fast (~400 tok/s)
5. **Claude 3.5 Sonnet** - Moderate (~300 tok/s)

### Reliability (Windows Stability)

1. **GPT-4o-mini** - Excellent ⭐⭐⭐⭐⭐
2. **GPT-4o** - Excellent ⭐⭐⭐⭐⭐
3. **Claude 3.5 Sonnet** - Excellent ⭐⭐⭐⭐⭐
4. **Qwen 2.5 Coder** - Good ⭐⭐⭐⭐ (occasional issues)

## Why GPT-4o-mini is Default

After testing, GPT-4o-mini provides the best balance:

✅ **Reliability**: No intermittent crashes or schema errors
✅ **Speed**: Fast enough for interactive use
✅ **Quality**: Excellent code generation for PV simulations
✅ **Cost**: Affordable for regular use (~2 cents per session)
✅ **Context**: Large enough for complex queries (128K tokens)

## Alternative Recommendations

### For Maximum Quality
Use **Claude 3.5 Sonnet** or **GPT-4o**:
```cmd
python -m agent.multi_agent_cli --model anthropic/claude-3.5-sonnet
```

### For Minimum Cost
Use **Qwen 2.5 Coder** or **Gemini Flash**:
```cmd
python -m agent.multi_agent_cli --model qwen/qwen-2.5-coder-32b-instruct
```

### For Maximum Speed
Use **GPT-4o-mini** (already default) or **Gemini Flash**:
```cmd
python -m agent.multi_agent_cli --model google/gemini-flash-1.5
```

## Testing Different Models

**Quick test**:
```cmd
REM Test GPT-4o-mini (default)
python -m agent.multi_agent_cli

REM Test GPT-4o (highest quality)
python -m agent.multi_agent_cli --model openai/gpt-4o

REM Test Claude 3.5 Sonnet
python -m agent.multi_agent_cli --model anthropic/claude-3.5-sonnet

REM Test Qwen 2.5 Coder (budget)
python -m agent.multi_agent_cli --model qwen/qwen-2.5-coder-32b-instruct
```

**Same query across models**:
```python
# Test query
"What's the annual energy for a 10kW system in Sydney?"
```

Compare:
- Response quality
- Code correctness
- Execution reliability
- Response time

## Model-Specific Notes

### GPT-4o-mini
- **Best for**: General use, production deployments
- **Strengths**: Fast, reliable, good quality, affordable
- **Weaknesses**: None significant

### GPT-4o
- **Best for**: Complex analysis, critical applications
- **Strengths**: Highest quality, excellent reasoning
- **Weaknesses**: 10x more expensive than mini

### Qwen 2.5 Coder 32B
- **Best for**: Budget-conscious users, code-heavy tasks
- **Strengths**: Code-specialized, cheapest option
- **Weaknesses**: Occasional Windows stability issues

### Claude 3.5 Sonnet
- **Best for**: Complex reasoning, long conversations
- **Strengths**: Best overall quality, largest context
- **Weaknesses**: Most expensive, slightly slower

## API Key Setup

All models use the same OpenRouter API key:

```cmd
setx OPENROUTER_API_KEY "sk-or-v1-YOUR-KEY-HERE"
```

Get a key at: https://openrouter.ai/

## Troubleshooting

### "Model not found" error

**Fix**: Check model name is correct. List available models:
```python
from agent.openrouter_client import OpenRouterClient
client = OpenRouterClient()
# Visit https://openrouter.ai/docs for model list
```

### Model too expensive

**Fix**: Switch to budget model:
```cmd
python -m agent.multi_agent_cli --model qwen/qwen-2.5-coder-32b-instruct
```

### Model too slow

**Fix**: Switch to faster model:
```cmd
python -m agent.multi_agent_cli --model openai/gpt-4o-mini
```

---

**Last Updated**: 2026-01-27
**Default Model**: openai/gpt-4o-mini
**Recommendation**: Keep default unless you have specific needs
