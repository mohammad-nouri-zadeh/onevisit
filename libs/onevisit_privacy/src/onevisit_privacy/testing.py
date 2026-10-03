"""Client finto per i test della pipeline privacy (storia C9). Nessuna chiamata di rete."""

from dataclasses import dataclass, field


@dataclass
class FakeCall:
    """Una chiamata registrata dal client finto."""

    model: str
    system: str
    prompt: str
    max_tokens: int


@dataclass
class FakeClaudeClient:
    """Restituisce le risposte in ordine e registra cosa riceve (per verificare la redazione)."""

    responses: list[str]
    calls: list[FakeCall] = field(default_factory=list)

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        """Registra la chiamata e restituisce la risposta successiva."""
        self.calls.append(FakeCall(model, system, prompt, max_tokens))
        if not self.responses:
            return "{}"
        return self.responses.pop(0)


# Alias con il nome indicato nel brief degli agenti.
FakeClient = FakeClaudeClient
