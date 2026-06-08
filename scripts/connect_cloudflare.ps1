param(
    [string]$ProjectName = $(if ($env:CF_PAGES_PROJECT_NAME) { $env:CF_PAGES_PROJECT_NAME } else { "sweetproduct" }),
    [string]$DatabaseName = "sp-profit-plan-holdings",
    [string]$MigrationPath = "migrations/0001_holdings.sql"
)

$ErrorActionPreference = "Stop"

if (-not $env:CLOUDFLARE_API_TOKEN) {
    throw "Set CLOUDFLARE_API_TOKEN in the current shell before running this script."
}
if (-not $env:CLOUDFLARE_ACCOUNT_ID) {
    throw "Set CLOUDFLARE_ACCOUNT_ID in the current shell before running this script."
}

$AccountId = $env:CLOUDFLARE_ACCOUNT_ID
$Headers = @{
    Authorization  = "Bearer $($env:CLOUDFLARE_API_TOKEN)"
    "Content-Type" = "application/json"
}

function Invoke-Cloudflare {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "https://api.cloudflare.com/client/v4$Path"
    $params = @{
        Method  = $Method
        Uri     = $uri
        Headers = $Headers
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
    }

    $response = Invoke-RestMethod @params
    if ($false -eq $response.success) {
        $messages = @($response.errors | ForEach-Object { $_.message }) -join "; "
        throw "Cloudflare API failed: $messages"
    }
    return $response.result
}

function Get-D1Database {
    param([string]$Name)
    $result = Invoke-Cloudflare -Method "GET" -Path "/accounts/$AccountId/d1/database"
    return @($result) | Where-Object { $_.name -eq $Name } | Select-Object -First 1
}

Write-Host "Checking Cloudflare D1 database '$DatabaseName'..."
$database = Get-D1Database -Name $DatabaseName
if (-not $database) {
    Write-Host "Creating D1 database '$DatabaseName'..."
    $database = Invoke-Cloudflare -Method "POST" -Path "/accounts/$AccountId/d1/database" -Body @{
        name = $DatabaseName
    }
}

$databaseId = if ($database.uuid) { $database.uuid } else { $database.id }
if (-not $databaseId) {
    throw "Could not determine D1 database id from Cloudflare response."
}

Write-Host "Applying D1 migration to '$DatabaseName'..."
$sql = Get-Content -LiteralPath $MigrationPath -Raw -Encoding UTF8
Invoke-Cloudflare -Method "POST" -Path "/accounts/$AccountId/d1/database/$databaseId/query" -Body @{
    sql = $sql
} | Out-Null

Write-Host "Checking Cloudflare Pages project '$ProjectName'..."
$project = $null
try {
    $project = Invoke-Cloudflare -Method "GET" -Path "/accounts/$AccountId/pages/projects/$ProjectName"
} catch {
    Write-Host "Creating Cloudflare Pages project '$ProjectName'..."
    $project = Invoke-Cloudflare -Method "POST" -Path "/accounts/$AccountId/pages/projects" -Body @{
        name              = $ProjectName
        production_branch = "master"
    }
}

$summary = [ordered]@{
    projectName = $ProjectName
    pagesUrl = "https://$ProjectName.pages.dev"
    databaseName = $DatabaseName
    databaseId = $databaseId
    requiredGitHubSecrets = @(
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_D1_DATABASE_ID"
    )
}

$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "cloudflare-connection.json" -Encoding UTF8

Write-Host ""
Write-Host "Cloudflare connection prepared."
Write-Host "Pages URL: $($summary.pagesUrl)"
Write-Host "D1 database id: $databaseId"
Write-Host "Saved non-secret summary to cloudflare-connection.json"
