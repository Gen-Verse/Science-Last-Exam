from .adapters.chat_completions import ChatModel


def create_model(config):
    if config.get("adapter") == "novita":
        from .adapters.novita import NovitaModel
        return NovitaModel(config)
    if config.get("adapter", "chat_completions") != "chat_completions":
        raise ValueError("Unsupported model adapter")
    return ChatModel(config)
