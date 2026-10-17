# Instala (ou reinstala) a geracao mensal das NFS-e prestadas da C3S no Windows.
#   powershell -ExecutionPolicy Bypass -File instalar-nfse-c3s.ps1
# Pede a senha do e-CNPJ A1 da C3S (arquivo .pfx), gera os PEM numa pasta so sua,
# clona o repositorio e cria a tarefa agendada (dia 1, 07:00; recupera se o PC estava desligado).
param(
    [string]$Pfx = "G:\Drives compartilhados\C3S Assessoria Contábil\CERTIFICADO C3S\C3S ASSESSORIA CONTABIL LTDA_47553447000151 (2).pfx"
)
$ErrorActionPreference = "Stop"
$base    = Join-Path $env:USERPROFILE "ferramentas-nfse-c3s"
$repo    = Join-Path $env:USERPROFILE "Site-dpa-nfse"
$openssl = "C:\Program Files\Git\mingw64\bin\openssl.exe"
if (-not (Test-Path $Pfx))     { throw "Certificado nao encontrado: $Pfx (use -Pfx <caminho>)" }
if (-not (Test-Path $openssl)) { throw "OpenSSL do Git nao encontrado: $openssl (instale o Git for Windows)" }

# 1) repositorio (branch com o codigo)
if (-not (Test-Path $repo)) {
    git clone --branch claude/monthly-bank-closure-automation-d1huvk https://github.com/juniosilva2609/Site-dpa.git $repo
} else { git -C $repo pull --ff-only }

# 2) certificado em PEM, pasta so do usuario
New-Item -ItemType Directory -Force "$base\cert", "$base\logs" | Out-Null
$seg = Read-Host "Senha do certificado e-CNPJ da C3S" -AsSecureString
$env:PFXPASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seg))
try {
    & $openssl pkcs12 -legacy -in $Pfx -passin env:PFXPASS -clcerts -nokeys -out "$base\cert\c3s_cert.pem"
    if ($LASTEXITCODE -ne 0) { throw "Senha errada ou certificado invalido (cert)." }
    & $openssl pkcs12 -legacy -in $Pfx -passin env:PFXPASS -nocerts -nodes -out "$base\cert\c3s_key.pem"
    if ($LASTEXITCODE -ne 0) { throw "Senha errada ou certificado invalido (chave)." }
} finally { Remove-Item Env:PFXPASS -ErrorAction SilentlyContinue }
icacls "$base\cert" /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" | Out-Null

# 3) script de execucao
Copy-Item "$repo\ferramentas\nfse-c3s\rodar-nfse-c3s.ps1" "$base\rodar-nfse-c3s.ps1" -Force

# 4) tarefa agendada
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>NFS-e prestadas da C3S (Portal Nacional) -> planilha de importacao do Alterdata.</Description></RegistrationInfo>
  <Triggers><CalendarTrigger>
    <StartBoundary>2026-11-01T07:00:00</StartBoundary><Enabled>true</Enabled>
    <ScheduleByMonth><DaysOfMonth><Day>1</Day></DaysOfMonth>
      <Months><January/><February/><March/><April/><May/><June/><July/><August/><September/><October/><November/><December/></Months>
    </ScheduleByMonth></CalendarTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable><ExecutionTimeLimit>PT1H</ExecutionTimeLimit><Enabled>true</Enabled></Settings>
  <Actions Context="Author"><Exec><Command>powershell.exe</Command>
    <Arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$base\rodar-nfse-c3s.ps1"</Arguments></Exec></Actions>
</Task>
"@
Register-ScheduledTask -TaskName "NFSe C3S - Alterdata" -Xml $xml -Force | Out-Null
Write-Host "Pronto. Proxima execucao:" (Get-ScheduledTaskInfo "NFSe C3S - Alterdata").NextRunTime
Write-Host "Para testar sem gravar no Drive: powershell -File `"$base\rodar-nfse-c3s.ps1`" -Competencia 2026-09 -Drive `"$env:TEMP\teste`""
