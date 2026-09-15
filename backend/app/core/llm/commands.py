import typer

from app.core.llm import service as llm_service
from app.core.llm.errors import LlmError

llm_app = typer.Typer()


def _usage_line(message) -> str:
    usage = llm_service.usage_of(message)
    cost = "unavailable" if usage.cost_usd is None else f"${usage.cost_usd:.6f}"
    return (
        f"tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
        f"total={usage.total_tokens} · cost: {cost}"
    )


@llm_app.command("chat")
def chat(
    prompt: str = typer.Argument(...),
    model: str | None = typer.Option(None, "--model"),
    temperature: float | None = typer.Option(None, "--temperature"),
    stream: bool = typer.Option(False, "--stream"),
    details: bool = typer.Option(False, "--details"),
) -> None:
    try:
        if stream:
            total = None
            for chunk in llm_service.chat_stream(prompt, model=model, temperature=temperature):
                typer.echo(chunk.text, nl=False)
                total = chunk if total is None else total + chunk
            typer.echo()
            typer.echo(_usage_line(total))
        else:
            message = llm_service.chat(prompt, model=model, temperature=temperature)
            typer.echo(message.text)
            typer.echo(_usage_line(message))
    except LlmError as exc:
        # One generic line for every failure class (← D2): `str(exc)` is
        # `LLM_FAILURE_MESSAGE` for the eight provider classes, or
        # `LlmConfigurationError`'s own message - the error code never
        # appears here either way.
        typer.echo(str(exc), err=True)
        if details:
            # Only the already-redacted, truncated `provider_message` may
            # reach the terminal. Never `.body`/`.headers`/`.raw_response`
            # (or the original exception) - those carry the OpenRouter API
            # key. `LlmConfigurationError` has no `provider_message`, hence
            # `getattr` with a `None` default.
            provider_message = getattr(exc, "provider_message", None)
            detail = (
                "the provider gave no message." if provider_message is None else provider_message
            )
            typer.echo(f"details: {detail}", err=True)
        raise typer.Exit(code=1) from exc
