param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$targetRoot = (Resolve-Path -LiteralPath $Destination).Path
$targetManifest = Join-Path $targetRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $targetManifest -PathType Leaf)) {
    throw 'Figma Desktop에서 Custom UI 플러그인을 먼저 만들고, 생성된 manifest.json이 있는 폴더를 지정하세요.'
}
$existing = Get-Content -LiteralPath $targetManifest -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $existing.id) { throw 'Figma가 발급한 플러그인 id가 없습니다. New plugin으로 먼저 생성하세요.' }
$template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$template | Add-Member -NotePropertyName id -NotePropertyValue $existing.id
$encoding = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($targetManifest, ($template | ConvertTo-Json -Depth 10), $encoding)
foreach ($file in @('code.js', 'ui.html')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $targetRoot $file) -Force
}
Write-Output '설치 완료. Figma Desktop에서 Plugins > Development > 모음 실시간 연결을 실행하세요.'
