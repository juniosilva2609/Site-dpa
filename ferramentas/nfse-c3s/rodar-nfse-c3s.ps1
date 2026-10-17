# NFS-e prestadas da C3S (Portal Nacional) -> planilha de importacao do Alterdata.
# Roda pela tarefa agendada "NFSe C3S - Alterdata" (dia 1, 07:00). Grava no Drive da C3S:
#   Financeiro C3S\Extratos\AAAA\MM\IMPORT ALTERDATA NFSE SERV PREST MM-AAAA.xlsx
param([string]$Competencia,   # AAAA-MM; vazio = mes anterior a hoje
      [string]$Drive)         # so para teste: pasta de destino alternativa

$ErrorActionPreference = "Stop"
$base   = "C:\Users\Junio\ferramentas-nfse-c3s"
$repo   = "C:\Users\Junio\Site-dpa-nfse"
$python = "C:\Users\Junio\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$drive0 = "G:\Drives compartilhados\C3S Interno\C3S - Interno\Financeiro C3S\Extratos"

$drive = if ($Drive) { $Drive } else { $drive0 }
if (-not $Competencia) { $Competencia = (Get-Date -Day 1).AddMonths(-1).ToString("yyyy-MM") }
$ano, $mes = $Competencia.Split("-")
$log = Join-Path $base "logs\$Competencia.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Tee-Object -FilePath $log -Append }

try {
    # Ao ligar o PC o Google Drive pode demorar a montar o G:
    for ($i = 0; $i -lt 40 -and -not (Test-Path $drive); $i++) { Start-Sleep -Seconds 15 }
    if (-not (Test-Path $drive)) { throw "Pasta do Drive nao encontrada: $drive" }

    $nome    = "IMPORT ALTERDATA NFSE SERV PREST $mes-$ano.xlsx"
    $destDir = Join-Path $drive "$ano\$mes"
    $destino = Join-Path $destDir $nome
    if (Test-Path $destino) { Log "Ja existia, nada a fazer: $destino"; exit 0 }

    Log "Competencia $Competencia"
    & git -C $repo pull --ff-only 2>&1 | ForEach-Object { Log "git: $_" }

    $env:DPA_C3S_NFSE_CERT = Join-Path $base "cert\c3s_cert.pem"
    $env:DPA_C3S_NFSE_KEY  = Join-Path $base "cert\c3s_key.pem"
    $tmp = Join-Path $env:TEMP "nfse-c3s-$Competencia"
    New-Item -ItemType Directory -Force $tmp | Out-Null

    Push-Location $repo
    $ErrorActionPreference = "Continue"
    $saida = & $python -m nfse.prestadas $Competencia $tmp 2>&1
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Pop-Location
    if ($codigo -ne 0) { throw "nfse.prestadas falhou: $($saida | Select-Object -Last 3 | Out-String)" }
    $resumo = $saida | Select-Object -Last 1
    Log "Resumo: $resumo"

    New-Item -ItemType Directory -Force $destDir | Out-Null
    $origem = Join-Path $tmp $nome
    Copy-Item $origem $destino
    if ((Get-FileHash $origem).Hash -ne (Get-FileHash $destino).Hash) { throw "Arquivo copiado diverge do gerado" }
    Log "Salvo: $destino"

    $j = $resumo | ConvertFrom-Json
    if ($j.clientes_sem_conta.Count -gt 0) { Log "ATENCAO: clientes sem conta (linhas amarelas): $($j.clientes_sem_conta | ConvertTo-Json -Compress)" }
    Remove-Item $tmp -Recurse -Force
} catch {
    Log "ERRO: $_"
    # Aviso na tela; a Rotina verificadora na nuvem (dias 1 e 3, 12:00) tambem avisa por e-mail se o arquivo nao existir
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Error
        $n.Visible = $true
        $n.ShowBalloonTip(20000, "NFS-e C3S - Alterdata", "Falhou em $Competencia. Veja $log", [System.Windows.Forms.ToolTipIcon]::Error)
        Start-Sleep -Seconds 21
        $n.Dispose()
    } catch {}
    exit 1
}
