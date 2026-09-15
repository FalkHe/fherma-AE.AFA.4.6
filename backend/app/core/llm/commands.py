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
) -> None:
    try:
        chat_model = llm_service.chat_model(model=model, temperature=temperature)

        if stream:
            total = None
            for chunk in chat_model.stream(prompt):
                typer.echo(chunk.text, nl=False)
                total = chunk if total is None else total + chunk
            typer.echo()
            typer.echo(_usage_line(total))
        else:
            message = chat_model.invoke(prompt)
            typer.echo(message.text)
            typer.echo(_usage_line(message))
    except LlmError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
