"""Automation helpers for publishing a new Patch GUI release.

Questo script orchestra le fasi principali del processo di rilascio:

1. Pulisce i branch locali mantenendo solo ``master`` e ``develop``.
2. Sincronizza i branch con ``origin`` e prepara ``master`` con uno
   *squash merge* da ``develop``.
3. Aggiorna i numeri di versione e il changelog.
4. Esegue i controlli indicati nella guida al rilascio.
5. Crea il commit di release, applica il tag e aggiorna ``develop``.

L'obiettivo è ridurre al minimo gli step manuali mantenendo un output
verboso per permettere all'operatore di seguire ogni operazione. Lo
script può essere eseguito in modalità "dry run" per verificare le
operazioni che verrebbero lanciate.

Uso rapido::

    python scripts/release_automation.py 1.2.3 \
        --next-dev-version 1.3.0.dev0 --push

Il comando aggiorna ``CHANGELOG.md``, ``pyproject.toml`` e
``patch_gui/_version.py`` alla versione ``1.2.3``, crea il tag ``v1.2.3``
per il commit su ``master`` e aggiorna ``develop`` alla versione di
sviluppo ``1.3.0.dev0``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
KEEP_BRANCHES = {"master", "develop"}
CODEX_PREFIX = "codex"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
VERSION_MODULE_PATH = REPO_ROOT / "patch_gui" / "_version.py"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

PYPROJECT_VERSION_RE = re.compile(r"^(version\s*=\s*)\"([^\"]+)\"", re.MULTILINE)
VERSION_MODULE_RE = re.compile(r"^(__version__\s*=\s*)\"([^\"]+)\"", re.MULTILINE)


class ReleaseError(RuntimeError):
    """Raised when a blocking precondition is not satisfied."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatizza il rilascio di Patch GUI")
    parser.add_argument("version", help="Versione da rilasciare (es. 1.2.3)")
    parser.add_argument(
        "--next-dev-version",
        dest="next_dev_version",
        help="Versione di sviluppo da impostare su develop dopo il rilascio (es. 1.3.0.dev0)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Esegue anche i push verso origin per branch e tag",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra le operazioni senza eseguirle realmente",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Salta l'esecuzione dei controlli (pytest, build, twine)",
    )
    return parser.parse_args(argv)


def run_cmd(
    cmd: Sequence[str],
    *,
    dry_run: bool,
    capture_output: bool = False,
    check: bool = True,
    cwd: Path | None = None,
) -> str:
    display = " ".join(cmd)
    print(f"$ {display}")
    if dry_run:
        return ""

    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        raise ReleaseError(f"Comando fallito ({display}): {stderr}")
    if capture_output:
        return (result.stdout or "").strip()
    return ""


def ensure_clean_worktree(*, dry_run: bool) -> None:
    if dry_run:
        print("[dry-run] Salto controllo stato working tree")
        return
    status = run_cmd(
        ["git", "status", "--porcelain"], dry_run=False, capture_output=True
    )
    if status:
        raise ReleaseError("La working tree contiene modifiche non committate")


def prune_local_branches(*, dry_run: bool) -> None:
    output = run_cmd(
        ["git", "branch", "--format", "%(refname:short)"],
        dry_run=dry_run,
        capture_output=not dry_run,
    )
    branches = output.splitlines() if output else []
    for branch in branches:
        branch = branch.strip()
        if not branch or branch in KEEP_BRANCHES:
            continue
        run_cmd(["git", "branch", "-D", branch], dry_run=dry_run)


def prune_remote_branches(*, dry_run: bool, remote: str = "origin") -> None:
    if dry_run:
        print(f"[dry-run] Analizzo i branch remoti su {remote}")
    output = run_cmd(
        ["git", "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}"],
        dry_run=False,
        capture_output=True,
    )
    branches = output.splitlines() if output else []
    for full_ref in branches:
        full_ref = full_ref.strip()
        if not full_ref or full_ref == f"{remote}/HEAD":
            continue
        try:
            _, branch = full_ref.split("/", 1)
        except ValueError:  # pragma: no cover - difesa extra
            continue
        if branch in KEEP_BRANCHES or not branch.startswith(CODEX_PREFIX):
            continue
        action = "Elimino" if not dry_run else "Eliminerei"
        print(f"{action} il branch remoto {branch} da {remote}")
        try:
            run_cmd(["git", "push", remote, "--delete", branch], dry_run=dry_run)
        except ReleaseError as error:
            print(
                "Impossibile completare l'eliminazione del branch "
                f"{branch}: {error}"
            )


def checkout_branch(branch: str, *, dry_run: bool) -> None:
    run_cmd(["git", "checkout", branch], dry_run=dry_run)


def pull_branch(branch: str, *, dry_run: bool) -> None:
    run_cmd(["git", "pull", "--ff-only", "origin", branch], dry_run=dry_run)


def merge_squash(source: str, *, dry_run: bool) -> None:
    run_cmd(["git", "merge", "--squash", source], dry_run=dry_run)


def update_pyproject(version: str, *, dry_run: bool) -> None:
    content = PYPROJECT_PATH.read_text(encoding="utf8")
    match = PYPROJECT_VERSION_RE.search(content)
    if not match:
        raise ReleaseError("Impossibile trovare il campo version in pyproject.toml")
    old_version = match.group(2)
    if old_version == version:
        print("pyproject.toml già impostato alla versione richiesta")
        return
    new_content = PYPROJECT_VERSION_RE.sub(rf"\1\"{version}\"", content, count=1)
    print(f"Aggiorno pyproject.toml: {old_version} -> {version}")
    if dry_run:
        return
    PYPROJECT_PATH.write_text(new_content, encoding="utf8")


def update_version_module(version: str, *, dry_run: bool) -> None:
    content = VERSION_MODULE_PATH.read_text(encoding="utf8")
    match = VERSION_MODULE_RE.search(content)
    if not match:
        raise ReleaseError("Impossibile trovare __version__ in patch_gui/_version.py")
    old_version = match.group(2)
    if old_version == version:
        print("patch_gui/_version.py già impostato alla versione richiesta")
        return
    new_content = VERSION_MODULE_RE.sub(rf"\1\"{version}\"", content, count=1)
    print(f"Aggiorno patch_gui/_version.py: {old_version} -> {version}")
    if dry_run:
        return
    VERSION_MODULE_PATH.write_text(new_content, encoding="utf8")


def normalize_block(block: list[str]) -> list[str]:
    trimmed = list(block)
    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def update_changelog(version: str, *, dry_run: bool) -> None:
    if not CHANGELOG_PATH.exists():
        raise ReleaseError("CHANGELOG.md non trovato")
    lines = CHANGELOG_PATH.read_text(encoding="utf8").splitlines()
    header = "## [Non rilasciato]"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration as exc:  # pragma: no cover - difesa extra
        raise ReleaseError(
            "Sezione [Non rilasciato] non trovata nel changelog"
        ) from exc

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## [") and idx != start:
            end = idx
            break

    block = normalize_block(lines[start + 1 : end])
    if not block:
        raise ReleaseError(
            "La sezione [Non rilasciato] è vuota: aggiungi le note prima del rilascio"
        )

    release_header = f"## [{version}] - {_dt.date.today().isoformat()}"
    new_lines: list[str] = []
    new_lines.extend(lines[:start])
    new_lines.append(header)
    new_lines.append("")
    new_lines.append(release_header)
    new_lines.extend(block)
    new_lines.append("")
    if end < len(lines) and lines[end].strip():
        new_lines.append("")
    new_lines.extend(lines[end:])

    print(f"Aggiorno CHANGELOG.md con la release {version}")
    if dry_run:
        return
    CHANGELOG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf8")


def stage_files(files: Iterable[Path], *, dry_run: bool) -> None:
    paths = [str(path.relative_to(REPO_ROOT)) for path in files]
    run_cmd(["git", "add", *paths], dry_run=dry_run)


def commit(message: str, *, dry_run: bool) -> None:
    run_cmd(["git", "commit", "-m", message], dry_run=dry_run)


def tag_version(version: str, *, dry_run: bool) -> None:
    run_cmd(
        ["git", "tag", "-a", f"v{version}", "-m", f"Patch GUI {version}"],
        dry_run=dry_run,
    )


def push_refs(*refs: str, dry_run: bool) -> None:
    for ref in refs:
        run_cmd(["git", "push", "origin", ref], dry_run=dry_run)


def run_checks(*, dry_run: bool) -> None:
    print("Eseguo i controlli di release…")
    commands: list[Sequence[str]] = [
        [sys.executable, "-m", "pytest"],
        [sys.executable, "-m", "build_translations"],
        [sys.executable, "-m", "build"],
    ]

    dist_dir = REPO_ROOT / "dist"
    artifacts = sorted(dist_dir.glob("*")) if dist_dir.exists() else []
    if artifacts:
        twine_args = [
            sys.executable,
            "-m",
            "twine",
            "check",
            *(str(a.relative_to(REPO_ROOT)) for a in artifacts),
        ]
        commands.append(twine_args)
    else:
        print(
            "Nessun artifact in dist/ – salto twine check finché non vengono generati"
        )

    for cmd in commands:
        if shutil.which(cmd[0] if os.path.sep in cmd[0] else cmd[0]) is None:
            print(f"[avviso] Comando non disponibile, salto: {' '.join(cmd)}")
            continue
        run_cmd(cmd, dry_run=dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"==> Preparazione release {args.version}")
    ensure_clean_worktree(dry_run=args.dry_run)

    print("==> Fetch e pulizia branch locali")
    run_cmd(["git", "fetch", "--all", "--prune"], dry_run=args.dry_run)
    prune_local_branches(dry_run=args.dry_run)
    print("==> Pulizia branch remoti")
    prune_remote_branches(dry_run=args.dry_run)

    print("==> Aggiorno develop")
    checkout_branch("develop", dry_run=args.dry_run)
    pull_branch("develop", dry_run=args.dry_run)

    print("==> Aggiorno master")
    checkout_branch("master", dry_run=args.dry_run)
    pull_branch("master", dry_run=args.dry_run)

    print("==> Squash merge da develop")
    merge_squash("develop", dry_run=args.dry_run)

    print("==> Aggiornamento versione e changelog")
    update_pyproject(args.version, dry_run=args.dry_run)
    update_version_module(args.version, dry_run=args.dry_run)
    update_changelog(args.version, dry_run=args.dry_run)

    if not args.skip_checks:
        run_checks(dry_run=args.dry_run)
    else:
        print("[avviso] Controlli disattivati con --skip-checks")

    print("==> Commit di release")
    stage_files(
        [PYPROJECT_PATH, VERSION_MODULE_PATH, CHANGELOG_PATH], dry_run=args.dry_run
    )
    commit(f"chore: release {args.version}", dry_run=args.dry_run)

    print("==> Creazione tag")
    tag_version(args.version, dry_run=args.dry_run)

    if args.push:
        print("==> Push dei riferimenti")
        push_refs("master", dry_run=args.dry_run)
        push_refs(f"v{args.version}", dry_run=args.dry_run)
    else:
        print(
            "[nota] Push saltato: lanciare manualmente 'git push origin master' e 'git push origin v{args.version}'"
        )

    print("==> Allineo develop al commit di release")
    checkout_branch("develop", dry_run=args.dry_run)
    run_cmd(["git", "merge", "--no-edit", "master"], dry_run=args.dry_run)

    if args.next_dev_version:
        print(f"==> Imposto versione di sviluppo {args.next_dev_version}")
        update_pyproject(args.next_dev_version, dry_run=args.dry_run)
        update_version_module(args.next_dev_version, dry_run=args.dry_run)
        stage_files([PYPROJECT_PATH, VERSION_MODULE_PATH], dry_run=args.dry_run)
        commit(
            f"chore: start development cycle {args.next_dev_version}",
            dry_run=args.dry_run,
        )
        if args.push:
            push_refs("develop", dry_run=args.dry_run)
        else:
            print(
                "[nota] Esegui 'git push origin develop' per aggiornare il branch remoto"
            )
    else:
        if args.push:
            push_refs("develop", dry_run=args.dry_run)
        else:
            print("[nota] Ricordati di eseguire 'git push origin develop'")

    print("==> Release completata! 🎉")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ReleaseError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1)
