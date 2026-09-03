"""LLM access layer: the OpenRouter model factory and the prompt loader.

Everything model-shaped in the application goes through this package —
`models.get_chat_model()` for chat completions and `prompts.render_prompt()`
for the version-controlled Markdown prompts. OpenRouter is the only gateway;
no module outside this package instantiates a chat model.
"""
