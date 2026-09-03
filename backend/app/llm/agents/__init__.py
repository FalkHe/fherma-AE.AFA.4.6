"""The advisor agent: the tool-calling loop and the tools it may call.

`tools/` holds the tool convention and one module per tool (step 3.11 onwards);
`advisor.py` is the loop that binds them to the model and is the only caller of
`tools.build_advisor_tools`. `chat_response_service` is the only caller of the
loop.
"""
