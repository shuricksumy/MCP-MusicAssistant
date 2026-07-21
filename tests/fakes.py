class FakeMAClient:
    """Stands in for MAClient.send() - returns canned data per WS command name."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def send(self, command: str, **kwargs) -> object:
        self.calls.append((command, kwargs))
        if command in self.responses:
            return self.responses[command]
        return None
