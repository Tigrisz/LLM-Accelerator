# Explicit-project rebuild; never sends commands to whichever GUI is open.
param(
    [ValidateSet(256,384)][int]$K = 256,
    [string]$PdsShellPath = 'D:\pango\PDS_2022.2-SP6.4\bin\pds_shell.exe',
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$taskRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskProjectDir = Join-Path $taskRepo "fpgatest\a_multigroup_k$K\prj"
$taskProject = Join-Path $taskProjectDir "a_multigroup_k$K.pds"
$taskTop = "a_multigroup_k${K}_uart_board_top"
if (!(Test-Path -LiteralPath $taskProject -PathType Leaf)) { throw "Project not found: $taskProject" }
if (!(Test-Path -LiteralPath $PdsShellPath -PathType Leaf)) { throw 'PDS shell executable not found' }
$taskConfig = Get-Content -LiteralPath $taskProject -Raw
if ($taskConfig -notmatch [regex]::Escape($taskTop) -or
    $taskConfig -notmatch 'selected_syn_tool_opt\s+\(_integer 2\)' -or
    $taskConfig -notmatch 'system_verilog\s+\(_switch ON\)') {
    throw 'Independent project must explicitly select its top, ADS and SystemVerilog'
}
$taskManifest = Get-Content -LiteralPath (Join-Path $taskProjectDir 'mem\manifest.json') -Raw | ConvertFrom-Json
if ($taskManifest.N -ne 3 -or $taskManifest.K -ne $K -or $taskManifest.input_kind -ne 'task_a_synthetic') {
    throw 'ROM metadata does not match the selected Task-A case'
}
$taskChecked = 0
foreach ($taskHash in $taskManifest.output_sha256.PSObject.Properties) {
    $taskRom = Join-Path $taskProjectDir ("mem\" + $taskHash.Name)
    if ((Get-FileHash -LiteralPath $taskRom -Algorithm SHA256).Hash -ne $taskHash.Value) {
        throw "ROM/config hash mismatch: $($taskHash.Name)"
    }
    $taskChecked++
}
$taskArguments = @('-project', $taskProject, '-run', 'gen_bit_stream')
if ($ValidateOnly) {
    [PSCustomObject]@{project=$taskProject; workdir=$taskProjectDir; top=$taskTop;
        expected_records=3*($K/128); rom_hash_checks=$taskChecked; arguments=$taskArguments} |
        ConvertTo-Json -Depth 3
    exit 0
}
if (!$env:PANGO_LICENSE_FILE) {
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE','User')
}
if (!$env:PANGO_LICENSE_FILE) { throw 'PDS license environment is not configured' }
Push-Location -LiteralPath $taskProjectDir
try {
    & $PdsShellPath @taskArguments
    $taskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $taskExitCode
