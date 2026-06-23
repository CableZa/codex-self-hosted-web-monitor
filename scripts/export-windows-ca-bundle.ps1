param(
    [string]$OutputPath = "certs/macos-ca-bundle.pem"
)

$ErrorActionPreference = "Stop"

$stores = @(
    "Cert:\CurrentUser\Root",
    "Cert:\CurrentUser\CA",
    "Cert:\LocalMachine\Root",
    "Cert:\LocalMachine\CA"
)

$outputDir = Split-Path -Parent $OutputPath
if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$seen = @{}
$certificates = New-Object System.Collections.Generic.List[System.Security.Cryptography.X509Certificates.X509Certificate2]

foreach ($store in $stores) {
    try {
        Get-ChildItem -Path $store -ErrorAction Stop | ForEach-Object {
            if ($_.NotAfter -lt (Get-Date)) {
                return
            }
            if (-not $seen.ContainsKey($_.Thumbprint)) {
                $seen[$_.Thumbprint] = $true
                $certificates.Add($_) | Out-Null
            }
        }
    }
    catch {
        Write-Warning "Could not read certificate store ${store}: $($_.Exception.Message)"
    }
}

if ($certificates.Count -eq 0) {
    throw "No certificates were exported from Windows certificate stores."
}

$builder = New-Object System.Text.StringBuilder
foreach ($cert in $certificates) {
    $base64 = [Convert]::ToBase64String($cert.RawData)
    [void]$builder.AppendLine("-----BEGIN CERTIFICATE-----")
    for ($index = 0; $index -lt $base64.Length; $index += 64) {
        $length = [Math]::Min(64, $base64.Length - $index)
        [void]$builder.AppendLine($base64.Substring($index, $length))
    }
    [void]$builder.AppendLine("-----END CERTIFICATE-----")
}

Set-Content -Path $OutputPath -Value $builder.ToString() -Encoding ascii
Write-Host "Wrote $OutputPath with $($certificates.Count) certificates."
