# Cópia de segurança criptografada das credenciais dos bancos.
#
#   Criar:     .\backup-credenciais.ps1 [-Pasta <pasta com os arquivos>]
#   Restaurar: .\backup-credenciais.ps1 -Restaurar <arquivo .zip.enc>
#
# Usa o OpenSSL que vem com o Git for Windows (AES-256-CBC + PBKDF2).
# A senha é pedida no terminal e não é gravada em lugar nenhum.

param(
    [string]$Pasta = "$env:USERPROFILE\Downloads\credenciais-para-colar",
    [string]$Restaurar
)

$ErrorActionPreference = "Stop"
$openssl = "C:\Program Files\Git\mingw64\bin\openssl.exe"
if (-not (Test-Path $openssl)) { throw "OpenSSL do Git não encontrado em $openssl" }

$seg = Read-Host "Senha do backup" -AsSecureString
$env:BKPASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seg))

try {
    if ($Restaurar) {
        $zip = $Restaurar -replace '\.enc$', ''
        & $openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in $Restaurar -out $zip -pass env:BKPASS
        if ($LASTEXITCODE -ne 0) { throw "Senha errada ou arquivo corrompido." }
        $destino = $zip -replace '\.zip$', ''
        Expand-Archive $zip -DestinationPath $destino -Force
        Remove-Item $zip
        Write-Host "Restaurado em: $destino"
    } else {
        $conf = Read-Host "Repita a senha" -AsSecureString
        $c = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($conf))
        if ($c -ne $env:BKPASS) { throw "As senhas não conferem." }
        $data = Get-Date -Format "yyyy-MM-dd"
        $zip = Join-Path (Split-Path $Pasta) "credenciais-$data.zip"
        Compress-Archive -Path "$Pasta\*" -DestinationPath $zip -Force
        & $openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -in $zip -out "$zip.enc" -pass env:BKPASS
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criptografar." }
        Remove-Item $zip
        Write-Host "Backup criado: $zip.enc"
        Write-Host "Guarde em dois lugares e a senha num gerenciador de senhas."
    }
} finally {
    Remove-Item Env:BKPASS -ErrorAction SilentlyContinue
}
