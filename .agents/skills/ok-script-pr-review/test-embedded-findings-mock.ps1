# Fixture-driven tests for Get-CodeRabbitEmbeddedFindings, which lives in
# coderabbit-review-helpers.ps1. Parses fixtures/review-body-sections.md
# directly so the assertions stay tied to a stable sample body.
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir 'coderabbit-review-helpers.ps1')

$fixture = Get-Content (Join-Path $scriptDir 'fixtures/review-body-sections.md') -Raw
$failed = 0
$checks = 0

function Assert-Equal {
    param($Expected, $Actual, [string]$Label)
    $script:checks++
    if ($Expected -ne $Actual) {
        $script:failed++
        Write-Host "FAIL $Label`: expected=$Expected actual=$Actual"
    } else {
        Write-Host "ok   $Label"
    }
}

# Case A: outside-diff section with 2 findings, then nitpick with 1.
$caseA = [regex]::Match($fixture, '(?s)## Case A.*?(?=\n## Case B)').Value
$findingsA = @(Get-CodeRabbitEmbeddedFindings ([pscustomobject]@{ id = 1; commit_id = 'a'; body = $caseA }))
Assert-Equal 3 $findingsA.Count 'A total findings'
Assert-Equal 2 @($findingsA | Where-Object { $_.kind -eq 'outsideDiff' }).Count 'A outsideDiff count'
Assert-Equal 1 @($findingsA | Where-Object { $_.kind -eq 'nitpick' }).Count 'A nitpick count'
$locationsA = ($findingsA | ForEach-Object { $_.location }) -join '|'
Assert-Equal 'src/app/main.py:105|src/app/main.py:140|src/app/util.py:12' $locationsA 'A locations (group summary skipped)'

# Case B: nitpick only, 2 findings, no outside diff.
$caseB = [regex]::Match($fixture, '(?s)## Case B.*?(?=\n## Case C)').Value
$findingsB = @(Get-CodeRabbitEmbeddedFindings ([pscustomobject]@{ id = 2; commit_id = 'b'; body = $caseB }))
Assert-Equal 2 $findingsB.Count 'B total findings'
Assert-Equal 0 @($findingsB | Where-Object { $_.kind -eq 'outsideDiff' }).Count 'B outsideDiff count'
Assert-Equal 2 @($findingsB | Where-Object { $_.kind -eq 'nitpick' }).Count 'B nitpick count'

# Case C: no embedded findings.
$caseC = [regex]::Match($fixture, '(?s)## Case C.*').Value
$findingsC = @(Get-CodeRabbitEmbeddedFindings ([pscustomobject]@{ id = 3; commit_id = 'c'; body = $caseC }))
Assert-Equal 0 $findingsC.Count 'C no findings'

Write-Host ""
if ($failed -gt 0) { Write-Host "$failed/$checks assertions failed"; exit 1 }
Write-Host "$checks assertions passed"
exit 0
