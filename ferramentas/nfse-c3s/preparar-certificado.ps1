# Gera os PEM de um e-CNPJ A1 (.pfx) para a geracao das NFS-e. Pede a senha no terminal.
#   powershell -ExecutionPolicy Bypass -File preparar-certificado.ps1 -Empresa licitprint -Pfx "J:\Meu Drive\Certificado Digital\LICITPRINT COMUNICACAO VISUAL LTDA65942303000179.pfx"
param(
    [Parameter(Mandatory)][ValidateSet("c3s","licitprint")][string]$Empresa,
    [Parameter(Mandatory)][string]$Pfx
)
$ErrorActionPreference = "Stop"
$base    = Join-Path $env:USERPROFILE "ferramentas-nfse-c3s"
$openssl = "C:\Program Files\Git\mingw64\bin\openssl.exe"
if (-not (Test-Path $Pfx))     { throw "Certificado nao encontrado: $Pfx" }
if (-not (Test-Path $openssl)) { throw "OpenSSL do Git nao encontrado: $openssl" }
New-Item -ItemType Directory -Force "$base\cert", "$base\logs" | Out-Null
$seg = Read-Host "Senha do certificado ($Empresa)" -AsSecureString
$env:PFXPASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seg))
try {
    & $openssl pkcs12 -legacy -in $Pfx -passin env:PFXPASS -clcerts -nokeys -out "$base\cert\${Empresa}_cert.pem"
    if ($LASTEXITCODE -ne 0) { throw "Senha errada ou certificado invalido." }
    & $openssl pkcs12 -legacy -in $Pfx -passin env:PFXPASS -nocerts -nodes -out "$base\cert\${Empresa}_key.pem"
    if ($LASTEXITCODE -ne 0) { throw "Senha errada ou certificado invalido." }
} finally { Remove-Item Env:PFXPASS -ErrorAction SilentlyContinue }
icacls "$base\cert" /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" | Out-Null
Write-Host "Pronto: $base\cert\${Empresa}_cert.pem e ${Empresa}_key.pem"
