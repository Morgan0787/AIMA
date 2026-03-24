# Jarvis v2 Core

## AI Provider Setup

The analysis step can use different AI backends via `config/settings.json`.

### Using Ollama

- `ai.provider = "ollama"`

### Using Gemini

- `ai.provider = "gemini"`
- Set `GEMINI_API_KEY` in PowerShell:
  `$env:GEMINI_API_KEY="your_key"`

### Using OpenAI

- `ai.provider = "openai"`
- Set `OPENAI_API_KEY` in PowerShell:
  `$env:OPENAI_API_KEY="your_key"`

