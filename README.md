# Helio — AI Companion for Solar PV Simulation

> Natural language interface for solar photovoltaic simulations using pvlib

<details open>
<summary><strong>Quick Start</strong></summary>

```cmd
# Install
install.bat

# Run
python -m agent.multi_agent_cli

# Try it
Helio> What's the annual energy for a 10kW system in Sydney?
```

</details>

## What is Helio?

Helio is an AI-powered companion that helps you run solar PV simulations using natural language. Just ask questions like:

- "What's the annual energy for a 10kW system in Tokyo?"
- "Compare 30° vs 45° tilt in Sydney"
- "What's the clipping loss for a 10kW DC / 8kW AC inverter?"

Helio translates your questions into pvlib code, executes it securely, validates the results, and explains the answer.

## Features

✅ **Natural language queries** - No coding required
✅ **Multi-agent architecture** - Router → SimAgent → QAAgent
✅ **Secure execution** - Sandboxed code execution with AST security checks
✅ **Physics validation** - Automatic consistency checks on results
✅ **Cross-platform** - Windows, Linux, macOS
✅ **Production-ready** - Comprehensive error handling and logging

## Installation

### Windows
```cmd
install.bat
```

### Linux/macOS
```bash
./install.sh
```

This installs:
- Python dependencies (pvlib, pandas, pydantic)
- Security sandbox (OS-specific)
- OpenRouter API client

## Setup

Set your OpenRouter API key:

```cmd
setx OPENROUTER_API_KEY "sk-or-v1-YOUR-KEY-HERE"
```

Get a key at: https://openrouter.ai/

## Usage

### Start Helio

```cmd
python -m agent.multi_agent_cli
```

You'll see:

```
 _   _      _ _
| | | | ___| (_) ___
| |_| |/ _ \ | |/ _ \
|  _  |  __/ | | (_) |
|_| |_|\___|_|_|\___/

PV Simulation Companion

Helio — AI Companion for Solar PV Simulation

Ask about yield, tilt, trackers, clipping, temperature, losses…
Type 'help' for examples, 'quit' to exit

Helio>
```

### Example Queries

**Annual Energy:**
```
Helio> What's the annual energy for a 10kW system in Sydney?
```

**Tilt Comparison:**
```
Helio> Compare tilt angles 20°, 30°, and 40° for a 10kW system in Madrid
```

**Tracking Systems:**
```
Helio> Compare single-axis tracking vs fixed tilt in Phoenix
```

**System Losses:**
```
Helio> What's the clipping loss for a 10kW DC / 8kW AC inverter?
```

**Monthly Profiles:**
```
Helio> Show monthly energy for a 10kW system in London
```

Type `help` to see more examples.

## Architecture

```
User Query
    ↓
Router Agent (classifies query)
    ↓
SimAgent (generates pvlib code)
    ↓
Secure Executor (runs code in sandbox)
    ↓
QA Agent (validates results)
    ↓
Natural Language Response
```

See [docs/multi-agent-architecture.md](docs/multi-agent-architecture.md) for details.

## Security

Helio uses multiple security layers:

**Pre-execution:**
- AST analysis (blocks eval/exec/__import__)
- Import allowlisting (only pvlib, pandas, numpy, etc.)
- Syntax validation

**During execution:**
- **Linux**: Bubblewrap (filesystem + network + PID isolation)
- **macOS**: sandbox-exec (Apple's sandbox)
- **Windows**: Enhanced subprocess (process isolation)

**Post-execution:**
- Physics validation (capacity factor, specific yield bounds)
- Output size limits
- Timeout enforcement

See [docs/security-implementation.md](docs/security-implementation.md) for details.

## Configuration

### Change Model

Default: `openai/gpt-4o-mini` (fast, reliable, cheap)

Try other models:

```cmd
# Highest quality
python -m agent.multi_agent_cli --model anthropic/claude-3.5-sonnet

# Budget option
python -m agent.multi_agent_cli --model qwen/qwen-2.5-coder-32b-instruct

# Best balance (default)
python -m agent.multi_agent_cli --model openai/gpt-4o-mini
```

See [docs/model-selection.md](docs/model-selection.md) for comparison.

### Specify venv

```cmd
python -m agent.multi_agent_cli --venv /path/to/venv
```

Auto-detects `sim_runtime/.venv` by default.

## Documentation

- [START_HERE.md](START_HERE.md) - Quick start guide
- [HELIO_REBRAND.md](HELIO_REBRAND.md) - Rebranding details
- [docs/multi-agent-architecture.md](docs/multi-agent-architecture.md) - System design
- [docs/security-implementation.md](docs/security-implementation.md) - Security details
- [docs/model-selection.md](docs/model-selection.md) - Model comparison
- [LATEST_FIXES.md](LATEST_FIXES.md) - Recent fixes and known issues
- [WINDOWS_FIX_SUMMARY.md](WINDOWS_FIX_SUMMARY.md) - Windows execution fixes

## Troubleshooting

### "Cannot connect to OpenRouter"
```cmd
echo %OPENROUTER_API_KEY%
setx OPENROUTER_API_KEY "sk-or-v1-YOUR-KEY-HERE"
```

### "ImportError: attempted relative import"
Use `python -m agent.multi_agent_cli` not `python agent/multi_agent_cli.py`

### Execution hanging on Windows
Fixed in latest version. See [WINDOWS_FIX_SUMMARY.md](WINDOWS_FIX_SUMMARY.md)

### Unicode errors in console
Fixed - all output is now ASCII-safe for Windows

## Development

### Run Tests
```cmd
pytest tests/ -v
```

### Enable Debug Mode
```python
agent = MultiAgentPV(debug=True)
```

### View Logs
Logs are in `runs/` directory with structured JSON format.

## Contributing

This is a research/educational project. Contributions welcome!

Key areas:
- Add more pvlib examples
- Improve error recovery
- Enhance physics validation
- Add more specialized agents

## License

MIT License - see LICENSE file

## Credits

- **pvlib-python**: Solar simulation library
- **OpenRouter**: LLM API aggregator
- **Pydantic**: Type-safe data validation
- **Rich**: Terminal formatting

## Support

- Issues: https://github.com/your-repo/issues
- Docs: [docs/](docs/)
- Latest fixes: [LATEST_FIXES.md](LATEST_FIXES.md)

---

**Helio** — AI Companion for Solar PV Simulation
Built with ❤️ for the solar community
