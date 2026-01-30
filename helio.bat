@echo off
REM Helio launcher batch script
REM This ensures helio runs even if Scripts directory isn't on PATH

python -m agent.multi_agent_cli %*
