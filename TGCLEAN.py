"""
TGClean
========================================
Deletes your messages, clears private chats, and leaves/deletes groups.

Setup:
    pip install -r requirements.txt

Get API credentials at: https://my.telegram.org -> API development tools
"""

import asyncio
import os
import sys

try:
    from telethon import TelegramClient
    from telethon.errors import (
        FloodWaitError,
        PasswordHashInvalidError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberBannedError,
        PhoneNumberInvalidError,
        PhoneNumberUnoccupiedError,
        SendCodeUnavailableError,
        SessionPasswordNeededError,
    )
    from telethon.tl.functions.channels import (
        DeleteChannelRequest,
        GetParticipantRequest,
        LeaveChannelRequest,
    )
    from telethon.tl.functions.messages import (
        DeleteChatRequest,
        DeleteHistoryRequest,
        GetFullChatRequest,
    )
    from telethon.tl.types import (
        Channel,
        ChannelParticipantCreator,
        Chat,
        ChatParticipantCreator,
        User,
    )
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
    from rich import box
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn,
    )
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────────────────────────

SESSION     = "tgclean_session"
ENV_FILE    = ".env"
MAX_RETRIES = 3

BANNER = (
    " ████████╗ ██████╗  ██████╗██╗     ███████╗ █████╗ ███╗   ██╗\n"
    "    ██╔══╝██╔════╝ ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║\n"
    "    ██║   ██║  ███╗██║     ██║     █████╗  ███████║██╔██╗ ██║\n"
    "    ██║   ██║   ██║██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║\n"
    "    ██║   ╚██████╔╝╚██████╗███████╗███████╗██║  ██║██║ ╚████║\n"
    "    ╚═╝    ╚═════╝  ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝\n"
)

console       = Console()
_logged_in_as = ""


# ── Screen helpers ────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def fresh_screen():
    clear()
    console.print(f"[bold purple]{BANNER}[/bold purple]")
    console.print(f"  [dim]Created By :[/dim] [bright_red]0xhex0rc1st[/bright_red]\n", highlight=False)
    if _logged_in_as:
        console.print(f"  [dim]Logged in as[/dim] [cyan]{_logged_in_as}[/cyan]\n")


def retry_label(n: int) -> str:
    return f"[bold]({n} {'retry' if n == 1 else 'retries'} left)[/bold]"


# ── Credentials ───────────────────────────────────────────────────────────────

def load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def save_env(api_id: str, api_hash: str):
    with open(ENV_FILE, "w") as f:
        f.write(f"TELEGRAM_API_ID={api_id}\n")
        f.write(f"TELEGRAM_API_HASH={api_hash}\n")


def get_credentials() -> tuple[int, str]:
    load_env()
    raw_id   = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if raw_id and api_hash:
        return int(raw_id), api_hash

    console.print(Panel(
        "[bold]First-time setup — Telegram API credentials[/bold]\n\n"
        "Get them at [cyan]https://my.telegram.org[/cyan] → API development tools",
        border_style="yellow",
    ))

    while True:
        raw_id = Prompt.ask("[bold]API ID[/bold]").strip()
        if raw_id.isdigit():
            break
        console.print("[red]API ID must be a number.[/red]")

    api_hash = Prompt.ask("[bold]API Hash[/bold]").strip()
    save_env(raw_id, api_hash)
    fresh_screen()
    console.print("[green]✓  Credentials saved.[/green]\n")
    return int(raw_id), api_hash


# ── Login ─────────────────────────────────────────────────────────────────────

async def login(client: TelegramClient) -> bool:
    global _logged_in_as
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        _logged_in_as = f"{me.first_name} (@{me.username})"
        return True

    signed_in = False

    while True:
        # ── Phone Number Step ────────────────────────────────────────────────────────
        already_sent = False
        while True:
            phone = Prompt.ask("[bold]Phone number[/bold] [dim](e.g. +14155552671)[/dim]")

            if not phone.startswith("+"):
                console.print("[red]Missing country code — must start with [bold]+[/bold] (e.g. +14155552671).[/red]")
                continue
            if not phone[1:].isdigit() or len(phone) < 8:
                console.print("[red]Invalid format — digits only after [bold]+[/bold] (e.g. +14155552671).[/red]")
                continue

            try:
                await client.send_code_request(phone)
                break
            except PhoneNumberInvalidError:
                console.print("[red]That number is not valid. Check it and try again.[/red]")
            except PhoneNumberUnoccupiedError:
                console.print("[red]That number is not registered on Telegram.[/red]")
            except PhoneNumberBannedError:
                console.print("[red]That number has been banned from Telegram.[/red]")
                return False
            except SendCodeUnavailableError:
                already_sent = True
                fresh_screen()
                console.print(Panel(
                    f"[yellow]A code was already sent to[/yellow] [bold cyan]{phone}[/bold cyan]\n"
                    "[dim]Enter the code you already received.[/dim]",
                    expand=False, border_style="yellow",
                ))
                break
            except FloodWaitError as e:
                console.print(f"[yellow]Too many attempts — wait {e.seconds}s then retry.[/yellow]")
                return False

        # ── Login Code Step ─────────────────────────────────────────────────────────
        if not already_sent:
            fresh_screen()
            console.print(Panel(
                f"[dim]Code sent to[/dim] [bold cyan]{phone}[/bold cyan]",
                expand=False, border_style="dim",
            ))

        go_back = False
        for attempt in range(1, MAX_RETRIES + 1):
            left = MAX_RETRIES - attempt
            code = Prompt.ask("[bold]Login code[/bold] [dim](or type [bold]back[/bold] to change number)[/dim]")

            if code.strip().lower() == "back":
                go_back = True
                fresh_screen()
                break

            try:
                await client.sign_in(phone, code)
                signed_in = True
                break
            except SessionPasswordNeededError:
                signed_in = True
                break
            except PhoneCodeExpiredError:
                console.print("[red]Code expired — restart to request a new one.[/red]")
                return False
            except PhoneCodeInvalidError:
                if left > 0:
                    console.print(f"[red]Wrong code — try again {retry_label(left)}[/red]")
                else:
                    console.print("[red]Wrong code — no retries left. Aborting.[/red]")
                    return False

        if go_back:
            continue
        break

    if not signed_in:
        return False

    # ── 2FA Step ──────────────────────────────────────────────────────────────
    if not await client.is_user_authorized():
        fresh_screen()
        console.print("[yellow]🔒  2FA enabled.[/yellow]\n")
        for attempt in range(1, MAX_RETRIES + 1):
            left = MAX_RETRIES - attempt
            password = Prompt.ask("[bold]2FA password[/bold]", password=True)
            try:
                await client.sign_in(password=password)
                break
            except PasswordHashInvalidError:
                if left > 0:
                    console.print(f"[red]Wrong password — try again {retry_label(left)}[/red]")
                else:
                    console.print("[red]Wrong password — no retries left. Aborting.[/red]")
                    return False

    me = await client.get_me()
    _logged_in_as = f"{me.first_name} (@{me.username})"
    return True


# ── Ownership Check ───────────────────────────────────────────────────────────

async def is_owner(client, entity) -> bool:
    try:
        me = await client.get_me()
        if isinstance(entity, Channel):
            p = await client(GetParticipantRequest(entity, me))
            return isinstance(p.participant, ChannelParticipantCreator)
        if isinstance(entity, Chat):
            full = await client(GetFullChatRequest(entity.id))
            for p in full.full_chat.participants.participants:
                if p.user_id == me.id:
                    return isinstance(p, ChatParticipantCreator)
    except Exception:
        pass
    return False


# ── Cleanup Steps ─────────────────────────────────────────────────────────────

async def delete_my_messages(client):
    console.rule("[bold cyan]Deleting your messages[/bold cyan]")
    total   = 0
    dialogs = [d async for d in client.iter_dialogs()]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                  TaskProgressColumn(), console=console, transient=True) as p:
        task = p.add_task("Scanning...", total=len(dialogs))
        for dialog in dialogs:
            chat = dialog.entity
            name = getattr(chat, "title", None) or getattr(chat, "first_name", "Unknown")
            p.update(task, description=f"[dim]{name[:45]}[/dim]")
            ids = [m.id async for m in client.iter_messages(chat, from_user="me")]
            for i in range(0, len(ids), 100):
                try:
                    await client.delete_messages(chat, ids[i:i+100], revoke=True)
                    total += len(ids[i:i+100])
                except Exception:
                    pass
                await asyncio.sleep(0.3)
            p.advance(task)

    console.print(f"[green]✓[/green]  Deleted [bold]{total}[/bold] messages.\n")
    return total


async def delete_private_chats(client):
    console.rule("[bold cyan]Clearing private chat histories[/bold cyan]")
    total   = 0
    dialogs = [d async for d in client.iter_dialogs() if isinstance(d.entity, User)]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                  TaskProgressColumn(), console=console, transient=True) as p:
        task = p.add_task("Processing...", total=len(dialogs))
        for dialog in dialogs:
            user = dialog.entity
            name = getattr(user, "first_name", "Unknown")
            p.update(task, description=f"[dim]{name[:45]}[/dim]")
            success = False

            try:
                await client(DeleteHistoryRequest(peer=user, max_id=0, just_clear=False, revoke=True))
                success = True
            except Exception:
                pass

            if not success:
                try:
                    await client.delete_dialog(user)
                    success = True
                except Exception:
                    pass

            if not success:
                try:
                    ids = [m.id async for m in client.iter_messages(user)]
                    if ids:
                        for i in range(0, len(ids), 100):
                            await client.delete_messages(user, ids[i:i+100], revoke=True)
                            await asyncio.sleep(0.2)
                    await client(DeleteHistoryRequest(peer=user, max_id=0, just_clear=True, revoke=False))
                    success = True
                except Exception:
                    pass

            if success:
                total += 1

            await asyncio.sleep(0.3)
            p.advance(task)

    console.print(f"[green]✓[/green]  Cleared [bold]{total}[/bold] private chats.\n")
    return total


async def leave_groups(client):
    console.rule("[bold cyan]Leaving groups & channels[/bold cyan]")
    left = deleted = 0
    dialogs = [d async for d in client.iter_dialogs() if not isinstance(d.entity, User)]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                  TaskProgressColumn(), console=console, transient=True) as p:
        task = p.add_task("Processing...", total=len(dialogs))
        for dialog in dialogs:
            entity = dialog.entity
            name   = getattr(entity, "title", "Unknown")
            p.update(task, description=f"[dim]{name[:45]}[/dim]")
            owner = await is_owner(client, entity)
            try:
                if owner:
                    if isinstance(entity, Channel):
                        await client(DeleteChannelRequest(entity))
                    elif isinstance(entity, Chat):
                        await client(DeleteChatRequest(chat_id=entity.id))
                    deleted += 1
                else:
                    if isinstance(entity, Channel):
                        await client(LeaveChannelRequest(entity))
                    elif isinstance(entity, Chat):
                        await client.delete_dialog(entity)
                    left += 1
            except Exception:
                pass
            await asyncio.sleep(0.5)
            p.advance(task)

    console.print(f"[green]✓[/green]  Left [bold]{left}[/bold] | Deleted (owned) [bold]{deleted}[/bold].\n")
    return left, deleted


def print_summary(msgs, chats, left, deleted):
    t = Table(title="[bold]Summary[/bold]", box=box.ROUNDED, header_style="bold magenta")
    t.add_column("Action", style="cyan")
    t.add_column("Count", justify="right", style="bold")
    t.add_row("Messages deleted",               str(msgs))
    t.add_row("Private chats cleared",          str(chats))
    t.add_row("Groups / channels left",         str(left))
    t.add_row("Groups / channels deleted (owned)", str(deleted))
    t.add_section()
    t.add_row("[bold]Total[/bold]", f"[bold]{msgs + chats + left + deleted}[/bold]")
    console.print(t)


# ── Menu ──────────────────────────────────────────────────────────────────────

MENU = [
    ("1", "Delete all my messages"),
    ("2", "Clear all private chat histories"),
    ("3", "Leave / delete all groups & channels"),
    ("4", "Full cleanup  (all of the above)"),
    ("─", ""),
    ("5", "Logout & remove session"),
    ("0", "Exit"),
]


def print_menu():
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("Key", style="bold cyan", width=3)
    t.add_column("Action")
    for key, label in MENU:
        if key == "─":
            t.add_row("[dim]─[/dim]", "")
        else:
            danger = key in ("1", "2", "3", "4")
            t.add_row(key, f"[{'red' if danger else 'dim'}]{label}[/]")
    console.print(t)


def danger_confirm(action: str) -> bool:
    console.print(Panel(
        f"[bold red]⚠  WARNING[/bold red]\n\n{action}\n\n[dim]This cannot be undone.[/dim]",
        border_style="red", expand=False,
    ))
    return Confirm.ask("[bold red]Continue?[/bold red]", default=False)


async def menu(client):
    while True:
        fresh_screen()
        print_menu()
        choice = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5"])

        if choice == "0":
            fresh_screen()
            console.print("[dim]Goodbye.[/dim]")
            break

        elif choice == "5":
            fresh_screen()
            if Confirm.ask("Remove saved session?", default=False):
                await client.log_out()
                for f in (f"{SESSION}.session", f"{SESSION}.session-journal"):
                    if os.path.exists(f):
                        os.remove(f)
                console.print("[green]✓  Logged out.[/green]")
                break

        elif choice == "1":
            fresh_screen()
            if danger_confirm("Delete ALL messages you have ever sent, everywhere."):
                fresh_screen()
                print_summary(await delete_my_messages(client), 0, 0, 0)
                Prompt.ask("\n[dim]Press Enter to return to menu[/dim]")

        elif choice == "2":
            fresh_screen()
            if danger_confirm("Delete ALL private chat histories."):
                fresh_screen()
                print_summary(0, await delete_private_chats(client), 0, 0)
                Prompt.ask("\n[dim]Press Enter to return to menu[/dim]")

        elif choice == "3":
            fresh_screen()
            if danger_confirm("Leave / delete ALL groups and channels."):
                fresh_screen()
                print_summary(0, 0, *await leave_groups(client))
                Prompt.ask("\n[dim]Press Enter to return to menu[/dim]")

        elif choice == "4":
            fresh_screen()
            if danger_confirm("Run FULL cleanup — messages, chats, and groups."):
                fresh_screen()
                msgs        = await delete_my_messages(client)
                chats       = await delete_private_chats(client)
                left, deld  = await leave_groups(client)
                print_summary(msgs, chats, left, deld)
                Prompt.ask("\n[dim]Press Enter to return to menu[/dim]")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    fresh_screen()
    api_id, api_hash = get_credentials()
    client = TelegramClient(SESSION, api_id, api_hash)

    if not await login(client):
        await client.disconnect()
        return

    await menu(client)
    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")