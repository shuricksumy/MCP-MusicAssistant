class FakeMAClient:
    """Stands in for MAClient.send() - returns canned data per WS command name."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def send(self, command: str, **kwargs) -> object:
        self.calls.append((command, kwargs))
        if command in self.responses:
            response = self.responses[command]
            # a callable response can raise or vary per call (e.g. fail once, then
            # succeed) - given the call count so far (including this one).
            if callable(response):
                return response(len([c for c in self.calls if c[0] == command]), kwargs)
            return response
        return None
