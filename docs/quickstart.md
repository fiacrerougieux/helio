# Quickstart Guide

Get started with Helio in 5 minutes!

## 1. Install

```bash
./install.sh   # or install.bat on Windows
```

## 2. Set API Key

```bash
export OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY-HERE"
```

## 3. Run Helio

```bash
python helio.py
```

## 4. Try Your First Query

```
Helio> What's the annual energy for a 10kW system in Sydney?
```

Helio will:
1. Understand your question
2. Generate Python code using pvlib
3. Execute it securely
4. Give you the answer in plain English

## 5. Explore More

Type `help` to see example queries:

```
Helio> help
```

## Example Queries

**Annual Energy:**
- "How much energy does a 5kW system produce in Berlin?"

**Tilt Optimization:**
- "What's the optimal tilt angle for Tokyo?"
- "Compare tilt angles 20°, 30°, and 40° in Madrid"

**Tracking:**
- "Compare single-axis tracking vs fixed tilt in Phoenix"

**System Losses:**
- "What's the clipping loss for a 10kW DC / 8kW AC inverter?"

**Monthly Profiles:**
- "Show monthly energy for a 10kW system in London"

## Tips

- Be specific about location and system size
- You can ask follow-up questions
- Type `quit` to exit

## Next Steps

- Read [model-selection.md](model-selection.md) to choose the best model
- Check [troubleshooting.md](troubleshooting.md) if you have issues

Happy simulating! ☀️
