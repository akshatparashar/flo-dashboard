"""FLO Assistant: answers questions about the dashboard from the dashboard's own numbers.

Read-only by design. The assistant never touches Google Sheets; it calls the same dashboard functions the pages use
(through a fetch callback that app.main hands it), so every figure it quotes is the figure on screen.

Understanding is rule based (text.py + engine.py), with no AI service needed. When the rules cannot work out a
question and GEMINI_API_KEY is set, a small Gemini model is asked only to map the question onto the dashboard's
labels (gemini.py). It never sees the data and never writes the answer.
"""
from .engine import Assistant

__all__ = ["Assistant"]
