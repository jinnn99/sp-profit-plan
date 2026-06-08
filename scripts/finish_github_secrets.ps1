param(
    [string]$ProjectName = $(if ($env:CF_PAGES_PROJECT_NAME) { $env:CF_PAGES_PROJECT_NAME } else { "sweetproduct" })
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$ghPath = Join-Path $repoRoot "tools\bin\gh.exe"
if (-not (Test-Path -LiteralPath $ghPath)) {
    throw "GitHub CLI was not found at tools\bin\gh.exe"
}
$ghPath = (Resolve-Path -LiteralPath $ghPath).Path

$summaryPath = Join-Path $repoRoot "cloudflare-connection.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "cloudflare-connection.json was not found. Run scripts\connect_cloudflare.ps1 first."
}
$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $summary.databaseId) {
    throw "D1 database id was not found in cloudflare-connection.json."
}

Write-Host ""
Write-Host "Finishing GitHub Secrets setup."
Write-Host "Cloudflare Pages URL: $($summary.pagesUrl)"
Write-Host "D1 database id: $($summary.databaseId)"
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

Write-Host "Setting GitHub repository secrets..."
$token | & $ghPath secret set CLOUDFLARE_API_TOKEN
$accountId | & $ghPath secret set CLOUDFLARE_ACCOUNT_ID
$summary.databaseId | & $ghPath secret set CLOUDFLARE_D1_DATABASE_ID
& $ghPath variable set CF_PAGES_PROJECT_NAME --body $ProjectName

Write-Host "Starting GitHub Actions deploy workflow..."
& $ghPath workflow run cloudflare-pages.yml --ref master

Write-Host ""
Write-Host "Done."
Write-Host "GitHub Actions: https://github.com/jinnn99/sp-profit-plan/actions"
Write-Host "Cloudflare Pages: $($summary.pagesUrl)"
