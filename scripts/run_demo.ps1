$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python -m equilibrium run examples/assist.eq --scenario examples/assist.scenario.json -o out/assist
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Start-Process (Join-Path (Get-Location) 'out/assist/report.html')

