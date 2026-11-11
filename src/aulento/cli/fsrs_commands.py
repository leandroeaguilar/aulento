"""Comandos CLI interactivos para el motor FSRS v5 y mazo de inglés técnico."""

from datetime import datetime, timezone
from typing import Optional
import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.panel import Panel

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.core.gemini_gateway import MENSAJE_CLAVE_ILEGIBLE, GeminiGateway
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import NOMBRE_VISIBLE
from aulento.core.secretos import SecretoIlegible
from aulento.db.connection import get_connection
from aulento.db.fsrs_repository import FSRSRepository
from aulento.fsrs.engine import FSRSEngine
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.fsrs.stats import get_full_fsrs_stats
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating
from aulento.vault.carpetas import carpetas_del_tutor
from aulento.vault.rutas import VaultNoDisponibleError, vault_de_la_cuenta
from aulento.audio.tts import TTSEngine, PronunciationRequest
from aulento.audio.gemini_tutor import (
    GeminiTutorClient,
    GeminiEvaluationRequest,
    save_gemini_api_key,
)

fsrs_app = typer.Typer(help="Motor de repetición espaciada FSRS v5 e inglés técnico profesional")
console = Console()

RATING_NAMES = {
    1: "[red]1: Again (Olvido)[/red]",
    2: "[yellow]2: Hard (Difícil)[/yellow]",
    3: "[green]3: Good (Bien)[/green]",
    4: "[bold cyan]4: Easy (Fácil)[/bold cyan]",
}


@fsrs_app.command("seed")
def cmd_fsrs_seed():
    """Siembra el banco de 100 colocaciones profesionales de inglés (BI, Cloud, IA)."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        total = seed_fsrs_deck(conn, cuenta.id)
        console.print(f"[bold green]✔[/bold green] Se sembraron [bold cyan]{total}[/bold cyan] colocaciones de inglés técnico profesional.")
    finally:
        conn.close()


@fsrs_app.command("status")
def cmd_fsrs_status():
    """Muestra el estado de la memoria FSRS, tarjetas vencidas hoy y racha diaria."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        stats = get_full_fsrs_stats(conn, cuenta.id)

        console.print(Panel(
            f"Tarjetas Totales: [bold white]{stats['total_cards']}[/bold white]  •  "
            f"Vencidas Hoy: [bold red]{stats['due_today']}[/bold red]  •  "
            f"Retención Histórica: [bold green]{stats['retention_rate']:.1f}%[/bold green]  •  "
            f"Racha: [bold yellow]{stats['streak_days']} días[/bold yellow]",
            title="🧠 Dashboard de Memoria FSRS v5 (Inglés Técnico)",
        ))

        table = Table(title="Distribución por Estado Cognitivo")
        table.add_column("Estado FSRS", style="cyan")
        table.add_column("Cantidad", justify="right", style="magenta")

        table.add_row("En Aprendizaje (Learning)", str(stats["learning"]))
        table.add_row("En Repaso / Dominadas (Review)", str(stats["review"]))
        table.add_row("En Reaprendizaje (Relearning)", str(stats["relearning"]))
        table.add_row("Total de Repasos Históricos", str(stats["total_reviews"]))

        console.print(table)

        if stats["categories"]:
            cat_table = Table(title="Colocaciones por Dominio Técnico")
            cat_table.add_column("Dominio", style="yellow")
            cat_table.add_column("Tarjetas", justify="right", style="green")
            for cat, count in stats["categories"].items():
                cat_table.add_row(cat.replace("_", " ").title(), str(count))
            console.print(cat_table)

    finally:
        conn.close()


@fsrs_app.command("list")
def cmd_fsrs_list(
    categoria: str = typer.Option(None, "--categoria", "-c", help="Filtrar por categoría"),
    limit: int = typer.Option(50, "--limit", "-n", help="Límite de tarjetas a mostrar"),
):
    """Lista las tarjetas y colocaciones del mazo de inglés."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = FSRSRepository(conn, cuenta.id)
        cards = repo.list_cards(categoria=categoria, limit=limit)

        table = Table(title=f"🗂 Mazo de Inglés Técnico ({len(cards)} tarjetas)")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Categoría", style="cyan")
        table.add_column("Pregunta / Contexto", style="white")
        table.add_column("Colocación en Inglés", style="bold green")
        table.add_column("Estabilidad (días)", justify="right", style="yellow")
        table.add_column("Repasos", justify="center", style="magenta")

        for c in cards:
            stab_str = f"{c.stability:.1f}d" if c.stability is not None else "-"
            table.add_row(
                str(c.id),
                c.categoria,
                c.item_pregunta,
                c.respuesta_esperada,
                stab_str,
                str(c.reps),
            )

        console.print(table)
    finally:
        conn.close()


@fsrs_app.command("add")
def cmd_fsrs_add(
    pregunta: str = typer.Option(..., "--pregunta", "-p", help="Contexto o pregunta en español"),
    respuesta: str = typer.Option(..., "--respuesta", "-r", help="Colocación exacta en inglés"),
    contexto: str = typer.Option(None, "--contexto", "-c", help="Ejemplo de uso en frase completa"),
    categoria: str = typer.Option("ingles_tecnico", "--categoria", help="Categoría temática"),
):
    """Agrega una nueva tarjeta al mazo de inglés técnico."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = FSRSRepository(conn, cuenta.id)
        card = repo.create_card(
            FSRSCardCreate(
                categoria=categoria,
                item_pregunta=pregunta,
                respuesta_esperada=respuesta,
                contexto_uso=contexto,
            )
        )
        console.print(f"[bold green]✔[/bold green] Tarjeta FSRS agregada con ID [cyan]{card.id}[/cyan]: [bold]{card.respuesta_esperada}[/bold].")
    finally:
        conn.close()


@fsrs_app.command("study")
def cmd_fsrs_study(
    limit: int = typer.Option(15, "--limit", "-n", help="Cantidad máxima de tarjetas a repasar en esta sesión"),
    level: str = typer.Option(None, "--level", "-l", help="Nivel de estudio: a1, a2, b1, b2, c1 o all"),
    auto_rating: int = typer.Option(None, "--auto-rating", help="Calificación automática para testing no interactivo (1-4)"),
):
    """Inicia la sesión de estudio diaria de 10-15 minutos con FSRS v5."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = FSRSRepository(conn, cuenta.id)
        engine = FSRSEngine(repo)
        due_cards = engine.get_session_cards(limit=limit, level=level)

        if not due_cards:
            console.print("[bold green]🎉 ¡Estás al día![/bold green] No tenés tarjetas pendientes de repaso para hoy.")
            return

        total_sesion = len(due_cards)
        level_txt = f" (Nivel Filtrado: {level})" if level else ""
        console.print(Panel(
            f"Tenés [bold cyan]{total_sesion}[/bold cyan] tarjetas pendientes en esta sesión{level_txt}.\n"
            f"Fórmulate la colocación mentalmente, revelá la solución y calificá tu memoria honestamente.",
            title="🎯 Sesión de Estudio FSRS: Inglés Técnico",
        ))

        repasadas = 0
        for idx, card in enumerate(due_cards, 1):
            console.print(f"\n[bold yellow]── Tarjeta {idx}/{total_sesion} • [{card.categoria}][/bold yellow]")
            console.print(Panel(f"[bold white]{card.item_pregunta}[/bold white]", title="Expresión / Reto"))

            # Revelar respuesta
            if auto_rating is None:
                typer.prompt("Presioná Enter para revelar la solución...", default="", show_default=False)

            console.print(f"👉 [bold green]{card.respuesta_esperada}[/bold green]")
            if card.contexto_uso:
                console.print(f"💡 [dim]{card.contexto_uso}[/dim]")

            # Calificar
            if auto_rating is not None:
                rating_val = auto_rating
            else:
                prompt_text = "Calificación:\n[1] Again (Olvido)  [2] Hard (Difícil)  [3] Good (Bien)  [4] Easy (Fácil)\nSelección [1-4]"
                rating_val = typer.prompt(prompt_text, default=3, type=int)

            if rating_val not in (1, 2, 3, 4):
                console.print("[red]Entrada inválida, registrando como 3 (Good).[/red]")
                rating_val = 3

            updated, log = engine.review(card.id, FSRSRating(rating_val))
            repasadas += 1

            stab_info = f"{updated.stability:.1f} días" if updated.stability else "inmediato"
            console.print(f"[dim]Próximo repaso programado con estabilidad: {stab_info}[/dim]")

        console.print(Panel(
            f"[bold green]✔ Sesión completada con éxito.[/bold green]\n"
            f"Repasaste [bold cyan]{repasadas}[/bold cyan] colocaciones técnicas.\n"
            f"Tu retención y curva de memoria han sido actualizadas.",
            title="🏆 Fin de la Sesión Diaria",
        ))

    finally:
        conn.close()


@fsrs_app.command("speak")
def cmd_fsrs_speak(
    item: str = typer.Argument(..., help="ID de la tarjeta FSRS o texto en inglés a vocalizar"),
    accent: str = typer.Option("en-US", "--accent", "-a", help="Acento: en-US (Americano) o en-GB (Británico)"),
    speed: float = typer.Option(1.0, "--speed", "-s", help="Velocidad: 0.75, 1.0, 1.25"),
):
    """Muestra la guía fonética IPA y metadatos de pronunciación de una colocación en inglés."""
    from aulento.audio.tts import TTSEngine, SpeechRequest

    text_to_speak = item
    context_str = None

    # Si es un número, buscar la tarjeta en la BD
    if item.isdigit():
        cuenta = cuenta_de_la_cli()
        conn = get_connection()
        try:
            repo = FSRSRepository(conn, cuenta.id)
            card = repo.get_card_by_id(int(item))
            if card:
                text_to_speak = card.respuesta_esperada
                context_str = card.contexto_uso
            else:
                console.print(f"[yellow]Tarjeta con ID {item} no encontrada. Vocalizando texto literal.[/yellow]")
        finally:
            conn.close()

    engine = TTSEngine()
    res = engine.synthesize(SpeechRequest(text=text_to_speak, accent=accent, speed=speed))

    flag = "🇺🇸" if res.accent == "en-US" else "🇬🇧"

    info = (
        f"[bold white text-lg]{res.text}[/bold white text-lg]\n\n"
        f"[bold cyan]Guía Fonética IPA:[/bold cyan] [green]{res.phonetic_guide}[/green]\n"
        f"[bold cyan]Acento:[/bold cyan] {flag} {res.accent}  |  "
        f"[bold cyan]Velocidad:[/bold cyan] {res.speed}x\n"
    )
    if context_str:
        info += f"\n[dim]Contexto: {context_str}[/dim]\n"

    info += (
        f"\n[dim italic]💡 Tip de Shadowing: Escucha la frase mentalmente e intenta repetirla en voz alta "
        f"imitando el ritmo y la entonación antes de verificar.[/dim italic]"
    )

    console.print(Panel(info, title="🔊 Vocalización y Drills de Inglés Técnico", border_style="cyan"))


@fsrs_app.command("levels")
def cmd_fsrs_levels():
    """Muestra el catálogo de los 5 niveles progresivos de inglés profesional y consultoría."""
    from aulento.fsrs.progressive_deck import LEVEL_METADATA
    table = Table(title="🎓 Programa Progresivo de Inglés (A1 ➔ C1 Consultoría IA)")
    table.add_column("Código", style="bold cyan")
    table.add_column("Nivel", style="bold white")
    table.add_column("Badge", style="magenta")
    table.add_column("Descripción", style="green")

    for k, v in LEVEL_METADATA.items():
        table.add_row(v["code"], v["name"], v["badge"], v["description"])

    console.print(table)


@fsrs_app.command("consulting")
def cmd_fsrs_consulting(
    scenario_id: str = typer.Option(None, "--scenario", "-s", help="ID del escenario (ej. fintech-reconciliation)"),
    response: str = typer.Option(None, "--response", "-r", help="Tu formulación en inglés"),
):
    """Ejecuta una simulación interactiva de consultoría en IA y llamadas de Discovery."""
    from aulento.fsrs.consulting_sim import ConsultingSimulator, ConsultingSubmission
    sim = ConsultingSimulator()

    if not scenario_id:
        scenarios = sim.list_scenarios()
        console.print("\n[bold cyan]Escenarios de Consultoría en IA Disponibles:[/bold cyan]")
        for i, s in enumerate(scenarios, 1):
            console.print(f"  [bold green]{i}. {s.id}[/bold green] — {s.title} ({s.industry})")
        selected = typer.prompt("\nSelecciona un escenario por ID", default=scenarios[0].id)
        scen = sim.get_scenario(selected)
    else:
        scen = sim.get_scenario(scenario_id)

    if not scen:
        console.print("[red]Escenario no encontrado.[/red]")
        return

    console.print(Panel(
        f"[bold white]{scen.title}[/bold white] ({scen.industry})\n"
        f"[bold cyan]Target:[/bold cyan] {scen.target_role}\n\n"
        f"[dim]{scen.client_background}[/dim]\n\n"
        f"[bold red]Dolor del Cliente:[/bold red] {scen.client_pain}\n\n"
        f"[bold yellow]Tu Desafío:[/bold yellow] {scen.challenge_prompt}",
        title="💼 Simulación de Consultoría IA",
        border_style="cyan"
    ))

    if not response:
        response = typer.prompt("Tu formulación en inglés profesional")

    sub = ConsultingSubmission(scenario_id=scen.id, user_response=response)
    feedback = sim.evaluate(sub)

    color = "green" if feedback.score >= 80 else ("yellow" if feedback.score >= 60 else "red")
    feedback_text = (
        f"[bold]Puntaje de Impacto:[/bold] [{color}]{feedback.score}/100[/{color}]  |  "
        f"[bold]Nivel de Solvencia:[/bold] {feedback.readiness_level}\n\n"
        f"[bold cyan]Tip de Consultoría Senior:[/bold cyan]\n{feedback.consulting_tip}\n\n"
        f"[bold magenta]Pulido de Krashen (i+1):[/bold magenta]\n[italic]{feedback.krashen_correction}[/italic]\n\n"
        f"[bold green]Respuesta Modelo Recomendada:[/bold green]\n«{feedback.recommended_model_answer}»"
    )
    console.print(Panel(feedback_text, title=f"Diagnóstico de Consultoría [{color}]{feedback.score}/100[/{color}]", border_style=color))


@fsrs_app.command("evaluate-pronunciation")
def cmd_fsrs_evaluate_pronunciation(
    expected: str = typer.Option(..., "--expected", "-e", help="Colocación o respuesta esperada"),
    spoken: str = typer.Option(..., "--spoken", "-s", help="Texto dictado o pronunciado por el usuario"),
    accent: str = typer.Option("en-US", "--accent", "-a", help="Acento objetivo ('en-US' o 'en-GB')"),
):
    """Evalúa la coincidencia fonética y léxica de lo pronunciado frente a la respuesta esperada."""
    engine = TTSEngine()
    eval_result = engine.evaluate_pronunciation(
        PronunciationRequest(expected_text=expected, spoken_text=spoken, accent=accent)
    )

    color = "green" if eval_result.accuracy_pct >= 85 else ("yellow" if eval_result.accuracy_pct >= 50 else "red")

    rating_labels = {1: "Again (1)", 2: "Hard (2)", 3: "Good (3)", 4: "Easy (4)"}
    rating_label = rating_labels.get(eval_result.suggested_rating, "Good (3)")

    summary_text = (
        f"[bold]Precisión Fonética:[/bold] [{color}]{eval_result.accuracy_pct}%[/{color}] ({eval_result.verdict})\n"
        f"[bold]Calificación FSRS Sugerida:[/bold] [bold cyan]{eval_result.suggested_rating}[/bold cyan] "
        f"([dim]{rating_label}[/dim])\n\n"
        f"[bold yellow]Texto Esperado:[/bold yellow] {eval_result.expected_text}\n"
        f"[bold cyan]Texto Pronunciado:[/bold cyan] {eval_result.spoken_text or '[dim](silencio / vacío)[/dim]'}\n\n"
        f"[bold magenta]Guía Fonética IPA:[/bold magenta] {eval_result.phonetic_guide}\n"
        f"[dim]Tip:[/dim] {eval_result.feedback_tip}"
    )

    console.print(Panel(summary_text, title=f"🎙️ Análisis de Pronunciación [{color}]{eval_result.accuracy_pct}%[/{color}]", border_style=color))


@fsrs_app.command("harvest")
def cmd_fsrs_harvest(
    source: str = typer.Option("vault", "--source", "-s", help="Canal de cosecha: 'vault', 'materiales' o 'ai'"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Tema o tecnología para IA o tema a buscar en los materiales"),
    level: str = typer.Option("b2_tech_data_ai", "--level", "-l", help="Nivel objetivo FSRS: a1..c1"),
    limit: int = typer.Option(10, "--limit", "-n", help="Número máximo de candidatos a extraer"),
    commit: bool = typer.Option(False, "--commit", "-c", help="Guardar automáticamente en SQLite las tarjetas válidas"),
    roadmap_id: Optional[int] = typer.Option(None, "--roadmap-id", help="Materiales: ruta cuyo perfil define el estilo y el mazo de las tarjetas"),
    material_id: Optional[int] = typer.Option(None, "--material-id", help="Materiales: id de un material del que cosechar"),
):
    """Cosecha flashcards técnicas desde el vault de la cuenta, sus materiales subidos o el generador IA."""
    from aulento.fsrs.harvester import OmniHarvester

    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        harvester = OmniHarvester()
        source_lower = source.lower().strip()

        pasarela = PasarelaDeIA(conn, cuenta.id)

        if source_lower == "vault":
            try:
                vault = vault_de_la_cuenta(conn, cuenta.id)
            except VaultNoDisponibleError as e:
                console.print(f"[bold red]✖ {escape(str(e))}[/bold red]", soft_wrap=True)
                raise typer.Exit(1) from None
            candidates = OmniHarvester(vault, carpetas_del_tutor(conn, cuenta.id)).harvest_from_vault(
                limit=limit, pasarela=pasarela
            )
        elif source_lower == "materiales":
            from aulento.fsrs.cloud_harvest import CosechaNoDisponibleError, RutaDeCosechaNoEncontradaError

            try:
                candidates = harvester.harvest_from_materials(
                    cuenta.id, query=topic or "", limit=limit, material_id=material_id, roadmap_id=roadmap_id, level=level
                )
            except (CosechaNoDisponibleError, RutaDeCosechaNoEncontradaError) as e:
                console.print(f"[yellow]No se pudo cosechar de tus materiales:[/yellow] {escape(str(e))}")
                raise typer.Exit(1)
        elif source_lower == "ai":
            candidates = harvester.harvest_from_ai(
                topic=topic or "Distributed Systems", level=level, count=limit, pasarela=pasarela
            )
        else:
            console.print(f"[red]Error: Origen '{source}' no válido. Use 'vault', 'materiales' o 'ai'.[/red]")
            raise typer.Exit(1)

        candidates = harvester.check_duplicates(conn, cuenta.id, candidates)

        table = Table(title=f"🌾 Harvester Omnicanal de Flashcards [{source.upper()}]")
        table.add_column("#", style="dim")
        table.add_column("Pregunta / Significado", style="bold white")
        table.add_column("Respuesta Esperada", style="bold cyan")
        table.add_column("Nivel", style="magenta")
        table.add_column("Estado", style="green")

        valid_cards = []
        for idx, card in enumerate(candidates, start=1):
            if card.is_duplicate:
                status_str = "[yellow]⚠️ Duplicada[/yellow]"
            else:
                status_str = "[green]✔ Nueva[/green]"
                valid_cards.append(card)

            table.add_row(
                str(idx),
                card.item_pregunta[:50] + ("..." if len(card.item_pregunta) > 50 else ""),
                card.respuesta_esperada,
                card.categoria,
                status_str,
            )

        console.print(table)

        if not candidates:
            console.print("[yellow]No se encontraron candidatos para los criterios especificados.[/yellow]")
            return

        if commit:
            if not valid_cards:
                console.print("[yellow]Todos los candidatos encontrados ya existen en el mazo FSRS.[/yellow]")
                return
            count = harvester.commit_harvest(conn, cuenta.id, valid_cards)
            console.print(f"[bold green]✔ Se importaron exitosamente {count} nuevas tarjetas al mazo FSRS.[/bold green]")
        else:
            console.print(
                f"\n[dim italic]💡 Se encontraron {len(valid_cards)} tarjetas nuevas de {len(candidates)} candidatos. "
                f"Usa '--commit' para guardarlas en la base de datos.[/dim italic]"
            )
    finally:
        conn.close()


@fsrs_app.command("gemini-config")
def cmd_fsrs_gemini_config(
    set_key: Optional[str] = typer.Option(None, "--set-key", "-k", help="Guardar nueva API Key de Google AI Studio"),
    status: bool = typer.Option(False, "--status", "-s", help="Ver estado de conexión con Gemini 1.5 Flash"),
):
    """Configura o inspecciona la clave de Google Gemini 1.5 Flash de la cuenta para evaluación de voz."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        if set_key:
            save_gemini_api_key(conn, cuenta.id, set_key)
            console.print(
                "[bold green]✔ Clave de Google AI Studio guardada exitosamente[/bold green] "
                f"(cifrada, para la cuenta {escape(cuenta.nombre_usuario)})."
            )
            return
        estado = GeminiGateway(conn, cuenta.id).get_status()
    finally:
        conn.close()

    configured = estado.has_free_key or estado.has_paid_key
    if estado.free_key_error or estado.paid_key_error:
        console.print(f"[bold red]✖ {MENSAJE_CLAVE_ILEGIBLE}[/bold red]")
        raise typer.Exit(code=1)

    mode_str = "[bold green]✨ Activo (Gemini 1.5 Flash Multimodal)[/bold green]" if configured else "[yellow]⚡ Fallback Local Heurístico (Sin clave)[/yellow]"
    masked_key = (estado.free_key_masked or estado.paid_key_masked) if configured else "(no configurada)"

    panel_text = (
        f"[bold]Modo de Evaluación:[/bold] {mode_str}\n"
        f"[bold]Modelo:[/bold] gemini-1.5-flash (Google AI Studio Free Tier)\n"
        f"[bold]API Key:[/bold] {masked_key}\n\n"
        "[dim]Para configurar tu clave gratuita obténla en https://aistudio.google.com y ejecuta:\n"
        "aulento fsrs gemini-config --set-key TU_API_KEY[/dim]"
    )
    console.print(Panel(panel_text, title="🤖 Estado del Tutor de Voz Gemini", border_style="cyan"))


@fsrs_app.command("gemini-evaluate")
def cmd_fsrs_gemini_evaluate(
    expected: str = typer.Option(..., "--expected", "-e", help="Frase objetivo en inglés"),
    spoken: str = typer.Option(..., "--spoken", "-s", help="Frase pronunciada o dictada"),
    context: str = typer.Option("shadowing", "--context", "-c", help="Contexto ('shadowing', 'discovery_call', 'pitch')"),
):
    """Evalúa la pronunciación y estilo de consultoría con la IA de la cuenta (su proveedor, su clave y su modelo)."""
    cuenta = cuenta_de_la_cli()
    req = GeminiEvaluationRequest(expected_text=expected, spoken_text=spoken, context_type=context)
    conn = get_connection()
    try:
        result = GeminiTutorClient.de_cuenta(conn, cuenta.id).evaluate(req)
    except SecretoIlegible:
        console.print(f"[bold red]✖ {MENSAJE_CLAVE_ILEGIBLE}[/bold red]")
        raise typer.Exit(code=1) from None
    finally:
        conn.close()

    score_color = "green" if result.accuracy_score >= 85 else ("yellow" if result.accuracy_score >= 65 else "red")
    if result.is_fallback:
        badge = "[bold yellow]⚡ Fallback Local[/bold yellow]"
    else:
        badge = f"[bold cyan]✨ {escape(NOMBRE_VISIBLE.get(result.provider_used or '', 'IA'))}[/bold cyan]"
    motivo = f"[bold]Sin IA:[/bold] {escape(result.motivo_sin_ia)}\n" if result.motivo_sin_ia else ""

    panel_text = (
        f"[bold]Motor Evaluador:[/bold] {badge} ({result.model_used})\n"
        f"{motivo}"
        f"[bold]Frase Esperada:[/bold] [italic white]{result.expected_text}[/italic white]\n"
        f"[bold]Frase Pronunciada:[/bold] [bold white]{result.spoken_text}[/bold white]\n\n"
        f"[bold]Precisión Fonética:[/bold] [{score_color}]{result.accuracy_score}/100 ({result.verdict})[/{score_color}]\n"
        f"[bold]Calificación FSRS Recomendada:[/bold] {RATING_NAMES.get(result.suggested_fsrs_rating, str(result.suggested_fsrs_rating))}\n\n"
        f"[bold cyan]Guía Fonética & Dicción:[/bold cyan]\n{result.phonetic_feedback}\n\n"
        f"[bold magenta]💡 Tip de Consultoría / Entonación C-Level:[/bold magenta]\n{result.consulting_tip}"
    )

    console.print(Panel(panel_text, title=f"[{score_color}]Evaluación de Voz: {result.verdict}[/{score_color}]", border_style=score_color))




