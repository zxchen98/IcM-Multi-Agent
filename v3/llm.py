"""Single shared Azure OpenAI chat model. The LLM does reasoning + routing only;
all data comes from MCP tools."""

import os
from langchain_openai import AzureChatOpenAI

_model = None


def get_model() -> AzureChatOpenAI:
    global _model
    if _model is None:
        _model = AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            temperature=0,  # deterministic routing
        )
    return _model
