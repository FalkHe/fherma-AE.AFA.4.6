from pathlib import Path

import typer

from app.core.llm import service as llm_service
from app.core.llm.errors import LlmError

llm_app = typer.Typer()


def _cost_text(usage) -> str:
    # Three cases, kept unambiguous (← gate fix): `None` stays "unavailable";
    # a genuine zero stays "$0.000000"; a non-zero cost that rounds to zero
    # at 6 decimals (embeddings routinely cost a fraction of a microdollar)
    # renders as "<$0.000001" instead of silently looking free. Anything
    # that already displays as non-zero at 6 decimals is untouched, so
    # `chat`'s existing `$0.000024`-style output is byte-identical.
    if usage.cost_usd is None:
        return "unavailable"
    if usage.cost_usd != 0 and round(usage.cost_usd, 6) == 0:
        return "<$0.000001"
    return f"${usage.cost_usd:.6f}"


def _usage_text(usage) -> str:
    cost = _cost_text(usage)
    return (
        f"tokens: prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
        f"total={usage.total_tokens} · cost: {cost}"
    )


def _usage_line(message) -> str:
    return _usage_text(llm_service.usage_of(message))


def _report_failure(exc: LlmError, *, details: bool) -> typer.Exit:
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
        detail = "the provider gave no message." if provider_message is None else provider_message
        typer.echo(f"details: {detail}", err=True)
    return typer.Exit(code=1)


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
        raise _report_failure(exc, details=details) from exc


@llm_app.command("embed")
def embed(
    texts: list[str] = typer.Argument(...),  # noqa: B008 - Typer's documented pattern
    model: str | None = typer.Option(None, "--model"),
    details: bool = typer.Option(False, "--details"),
) -> None:
    try:
        result = llm_service.embed_texts(texts, model=model)
        for index, vector in enumerate(result.vectors, start=1):
            typer.echo(f"vector {index}: length={len(vector)}")
        cost = _cost_text(result.usage)
        typer.echo(
            f"tokens: prompt={result.usage.prompt_tokens} total={result.usage.total_tokens} "
            f"· cost: {cost}"
        )
    except LlmError as exc:
        raise _report_failure(exc, details=details) from exc


@llm_app.command("image")
def image(
    prompt: str = typer.Argument(...),
    out: Path = typer.Option(..., "--out"),  # noqa: B008 - Typer's documented pattern
    model: str | None = typer.Option(None, "--model"),
    details: bool = typer.Option(False, "--details"),
) -> None:
    # Validated before any network call (← research.md): a bad path must
    # never spend the ~$0.067 an image call costs.
    parent = out.parent
    if not parent.is_dir():
        raise typer.BadParameter(f"parent directory does not exist: {parent}", param_hint="--out")

    try:
        result = llm_service.generate_image(prompt, model=model)
    except LlmError as exc:
        raise _report_failure(exc, details=details) from exc

    usage_text = _usage_text(result.usage)
    try:
        out.write_bytes(result.image_bytes)
    except OSError as exc:
        # The call was already paid for, so the cost is reported on stdout
        # even though the write itself failed.
        typer.echo(usage_text)
        typer.echo(f"{out}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"wrote {out} ({len(result.image_bytes)} bytes, {result.media_type})")
    typer.echo(usage_text)
