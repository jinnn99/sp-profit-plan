param(
    [string]$ProjectName = $(if ($env:CF_PAGES_PROJECT_NAME) { $env:CF_PAGES_PROJECT_NAME } else { "sweetproduct" })
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$GhExe = Join-Path $repoRoot "tools\bin\gh.exe"
if (-not (Test-Path -LiteralPath $GhExe)) {
    throw "GitHub CLI was not found at tools\bin\gh.exe"
}
$GhExe = (Resolve-Path -LiteralPath $GhExe).Path

Write-Host ""
Write-Host "Cloudflare + GitHub 연결을 시작합니다."
Write-Host "무료 리소스만 사용합니다: Cloudflare Pages, Pages Functions, D1, GitHub Actions."
Write-Host ""
Write-Host "필요한 Cloudflare API token 권한:"
Write-Host "- Account / Cloudflare Pages / Edit"
Write-Host "- Account / D1 / Edit"
Write-Host ""

$accountId = Read-Host "Cloudflare Account ID"
$secureToken = Read-Host "Cloudflare API Token" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if (-not $accountId -or -not $token) {
    throw "Account ID and API token are required."
}

$env:CLOUDFLARE_ACCOUNT_ID = $accountId
$env:CLOUDFLARE_API_TOKEN = $token
$env:CF_PAGES_PROJECT_NAME = $ProjectName

& "$PSScriptRoot\connect_cloudflare.ps1" -ProjectName $ProjectName

$summary = Get-Content -LiteralPath "cloudflare-connection.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $summary.databaseId) {
    throw "D1 database id was not written to cloudflare-connection.json."
}

Write-Host ""
Write-Host "GitHub Secrets를 설정합니다..."
$token | & $GhExe secret set CLOUDFLARE_API_TOKEN
$accountId | & $GhExe secret set CLOUDFLARE_ACCOUNT_ID
$summary.databaseId | & $GhExe secret set CLOUDFLARE_D1_DATABASE_ID
& $GhExe variable set CF_PAGES_PROJECT_NAME --body $ProjectName

Write-Host ""
Write-Host "GitHub Actions 배포를 실행합니다..."
& $GhExe workflow run cloudflare-pages.yml --ref master

Write-Host ""
Write-Host "연결 요청이 완료되었습니다."
Write-Host "GitHub Actions: https://github.com/jinnn99/sp-profit-plan/actions"
Write-Host "Cloudflare Pages 예상 주소: https://$ProjectName.pages.dev"
Write-Host "잠시 후 Actions 실행 결과와 API 상태를 확인하세요."
