# Troubleshooting

## Common Issues

### Installation Problems

**"Python not found"**
- Install Python 3.9+ from [python.org](https://python.org)
- On Windows, check "Add Python to PATH" during installation

**"pip not found"**
- Python 3.9+ includes pip
- If missing: `python -m ensurepip --upgrade`

### API Issues

**"Cannot connect to OpenRouter"**

Check your API key:
```bash
# Windows
echo %OPENROUTER_API_KEY%

# Linux/macOS
echo $OPENROUTER_API_KEY
```

Get a key at [openrouter.ai](https://openrouter.ai/)

**"Rate limit exceeded"**
- You've hit OpenRouter's rate limit
- Wait a few minutes or upgrade your plan

### Runtime Errors

**"Syntax Error: unexpected indent"**

This is a known issue with gpt-4o-mini. Solutions:
1. Just retry the query (works 70-80% of the time)
2. Switch to a better model:
   ```bash
   python helio.py --model qwen/qwen-2.5-coder-32b-instruct
   ```

**"Compliance Check Failed"**
- The LLM tried to use an unsafe function
- This is a security feature - query will be retried
- If it persists, try rephrasing your question

**"Execution timeout"**
- Your query is taking too long (>60s)
- Try a simpler query or shorter time period
- Monthly data is faster than hourly

### Platform-Specific

**Windows: "UnicodeEncodeError"**
- Fixed in latest version
- Make sure you're on v0.3.0+

**Linux: Permission denied on install.sh**
```bash
chmod +x install.sh
./install.sh
```

**macOS: "command not found"**
- Add Python to PATH:
  ```bash
  export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:$PATH"
  ```

## Getting Help

1. Check if your issue is listed above
2. Try the query again (many errors are transient)
3. Switch models if gpt-4o-mini is causing problems
4. Open an issue on GitHub with:
   - Your OS and Python version
   - The exact error message
   - The query you tried

## Tips for Success

✅ **Do:**
- Be specific with locations and dates
- Use standard city names (Sydney, Tokyo, Berlin)
- Start simple, then add complexity
- Try different models if one fails

❌ **Don't:**
- Use very long time periods (>1 year)
- Ask vague questions without location/system size
- Run multiple queries simultaneously
- Share your API key publicly
