TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "dummy_echo",
            "description": "Dummy tool to echo a message back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo"}
                },
                "required": ["text"]
            }
        },
        "handler": lambda text: {"echo": text}
    }
]
