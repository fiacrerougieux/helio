# Installation Guide

## Requirements

- Python 3.9 or higher
- OpenRouter API key ([Get one here](https://openrouter.ai/))

## Quick Install

### Windows

```cmd
install.bat
```

### Linux/macOS

```bash
./install.sh
```

## Setup API Key

After installation, set your OpenRouter API key:

### Windows

```cmd
setx OPENROUTER_API_KEY "sk-or-v1-YOUR-KEY-HERE"
```

### Linux/macOS

```bash
echo 'export OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY-HERE"' >> ~/.bashrc
source ~/.bashrc
```

## Verify Installation

```bash
python helio.py
```

You should see the Helio welcome screen. Type `help` to see example queries.

## Troubleshooting

**"Cannot connect to OpenRouter"**
- Check your API key is set: `echo %OPENROUTER_API_KEY%` (Windows) or `echo $OPENROUTER_API_KEY` (Linux/macOS)
- Verify the key is correct on [OpenRouter](https://openrouter.ai/)

**"Import Error"**
- Make sure you run `python helio.py` not `python agent/multi_agent_cli.py`
- Check Python version: `python --version` (must be 3.9+)

**For more help, open an issue on GitHub**
