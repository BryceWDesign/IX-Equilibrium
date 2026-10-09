# Windows and GitHub handoff

The ZIP is a repository-ready source release. No GitHub push or remote CI run
was performed during its creation. The original donor archives were not changed.

## Run before installing anything

Extract the ZIP, then open PowerShell in the folder containing `pyproject.toml`:

```powershell
python --version
python -m unittest discover
python scripts/quality_gate.py --output out/quality.json
python -m equilibrium run examples/assist.eq --scenario examples/assist.scenario.json -o out/assist
Start-Process .\out\assist\report.html
```

Requires Python 3.11+. If `python` selects the wrong installation, use
`py -3.13` in place of `python` in these commands. There are no runtime packages
to install. The reference code was tested locally on Linux with Python 3.12.14;
your Windows run and the remote CI matrix are separate checks.

Optional isolated installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps .
.\.venv\Scripts\python.exe -m equilibrium --version
```

The supplied wheel can also be installed directly with `pip install --no-deps`
and its full filename. Source mode is sufficient for the demos and all tests.
The PowerShell demo launcher is `scripts/run_demo.ps1`; running Python directly
works without changing any PowerShell execution policy.

## Populate your existing empty IX-Equilibrium repository

Keep the extracted release separate from the Git clone. These examples use
your Downloads directory; edit only the release path if you extracted elsewhere.

```powershell
Set-Location "$env:USERPROFILE\Downloads"
git clone https://github.com/BryceWDesign/IX-Equilibrium.git
Set-Location .\IX-Equilibrium
```

An empty-repository warning during clone is expected. Copy the **contents** of
the extracted source folder into this clone, including `.github`, `.gitignore`
and `.gitattributes`. Retain the clone's existing `.git` directory. For example:

```powershell
$releasePath = "$env:USERPROFILE\Downloads\IX-Equilibrium-v0.1.0\IX-Equilibrium"
Get-ChildItem -LiteralPath $releasePath -Force |
    Where-Object { $_.Name -ne '.git' } |
    Copy-Item -Destination (Get-Location) -Recurse -Force
```

Confirm the copied files before committing:

```powershell
python scripts/quality_gate.py --output out/quality.json
git status --short
git add .
git diff --cached --stat
git commit -m "Release IX-Equilibrium v0.1.0 checked coordination language"
git branch -M main
git push -u origin main
```

If any check fails, fix or report that failure before the commit/push steps.
These instructions assume the repository is still empty. If it now contains
work, review that work and merge intentionally rather than overwriting it.
`out/`, local journals, virtual environments and build products are ignored.

Open GitHub's Actions tab after the push and wait for all six configured jobs
(Ubuntu/Windows, Python 3.11/3.12/3.13). A local PASS does not establish that
those remote jobs are green. The workflow uploads its actual validation output.

After CI is green, optional tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

GitHub About:

> A programming language for human-AI-robot coordination, adaptive sensor meshes, and verifiable physical actions under explicit constraints.

Suggested topics: `programming-language`, `robotics`, `human-robot-interaction`,
`sensor-fusion`, `capabilities`, `runtime-assurance`, `deterministic-simulation`,
`apache-2-0`.

The About text describes the intended domain. The README and language reference
state the exact implemented software scope. Apache 2.0 applies to the new
release, including commercial use subject to that license's terms.
