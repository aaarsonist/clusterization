# Создание файла .env со случайными секретами при первом запуске (Windows PowerShell 5.1+).
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Write-Host '[OK] Файл .env уже существует, ключи сохраняются.'
    exit 0
}
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
function New-Secret([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $rng.GetBytes($buffer)
    return [Convert]::ToBase64String($buffer)
}
$lines = @(
    ('# Сгенерировано start.bat ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')),
    'POSTGRES_USER=postgres',
    ('POSTGRES_PASSWORD=' + ((New-Secret 24) -replace '[^A-Za-z0-9]', 'x')),
    'POSTGRES_DB=loyalty_db',
    ('JWT_SECRET_KEY=' + (New-Secret 48)),
    ('PII_ENCRYPTION_KEY=' + (New-Secret 32)),
    ('PII_HMAC_KEY=' + (New-Secret 32)),
    ('BACKUP_ENCRYPTION_KEY=' + (New-Secret 32)),
    'CORS_ORIGINS=https://localhost:8443'
)
[System.IO.File]::WriteAllText($envFile, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
Write-Host '[OK] Создан файл .env со случайными ключами шифрования.'
