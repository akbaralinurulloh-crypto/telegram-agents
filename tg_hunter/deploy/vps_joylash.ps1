# TG Hunter: noutbukdan VPS ga bir bosishda joylash (Windows PowerShell 5.1+).
# Ishga tushirish: VPSGA_JOYLASH.bat ni ikki marta bosing.
# Qadamlar: IP -> ulanishni sinash -> noutbukdagi agentni to'xtatish -> Telegramga yangi kirish -> serverga yuborish -> serverda o'rnatish.
# Faqat ASCII: Windows konsolida o'zbekcha apostroflar buzilmasligi uchun.

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Root = Split-Path -Parent $PSScriptRoot      # tg_hunter papkasi (ichida docker-compose.yml)
$Remote = "/opt/tg_hunter"
$Key = Join-Path (Join-Path $HOME ".ssh") "hunter_vps"
$Temp = [System.IO.Path]::GetTempPath()
$Total = 6

function Pick([string]$winPath, [string]$name) {
    if (Test-Path $winPath) { return $winPath }
    return $name
}
# Windows'ning o'z OpenSSH/tar dasturlari (Git yoki boshqa dasturlarning chalkash versiyalari o'rniga)
$Ssh = Pick (Join-Path $env:SystemRoot "System32\OpenSSH\ssh.exe") "ssh"
$Scp = Pick (Join-Path $env:SystemRoot "System32\OpenSSH\scp.exe") "scp"
$Tar = Pick (Join-Path $env:SystemRoot "System32\tar.exe") "tar"
$SshOpts = @("-i", $Key, "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30")

function Say([string]$msg, [string]$color = "White") { Write-Host $msg -ForegroundColor $color }
function Step([int]$n, [string]$msg) { Write-Host ""; Write-Host ("[{0}/{1}] {2}" -f $n, $Total, $msg) -ForegroundColor Cyan }
function Fail([string]$msg) { Write-Host ""; Write-Host ("XATO: " + $msg) -ForegroundColor Red; exit 1 }
function Test-Ip([string]$s) {
    if ($s -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { return $false }
    foreach ($p in $s.Split('.')) { if ([int]$p -gt 255) { return $false } }
    return $true
}

Say "==== TG Hunter: VPS ga joylash ====" "Yellow"
if (-not (Test-Path (Join-Path $Root "docker-compose.yml"))) { Fail "docker-compose.yml topilmadi ($Root). Bu fayl tg_hunter papkasining ichida turishi kerak." }
if (-not (Test-Path (Join-Path $Root ".env"))) { Fail ".env topilmadi ($Root)." }
if (-not (Test-Path $Key)) { Fail "SSH kaliti topilmadi: $Key" }
foreach ($c in @($Ssh, $Scp, $Tar, "docker")) {
    if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Fail "'$c' dasturi topilmadi." }
}

# ---------------------------------------------------------------- 1. IP
Step 1 "Serverning IP raqami"
$IP = ""
for ($i = 1; $i -le 3; $i++) {
    $ans = (Read-Host "Hetzner'dagi serverning IPv4 raqamini kiriting (4 ta raqam, nuqtalar bilan)").Trim()
    if (-not (Test-Ip $ans)) { Say "Bu IP ga o'xshamayapti: faqat raqamlar va nuqtalar bo'lsin (masalan 203.0.113.25)." "Yellow"; continue }
    if ($ans.StartsWith("203.0.113.")) { Say "Bu namuna IP. Hetzner panelidagi o'zingizning serveringiz IP sini kiriting." "Yellow"; continue }
    $IP = $ans
    break
}
if (-not $IP) { Fail "IP kiritilmadi." }

# ---------------------------------------------------------------- 2. Ulanishni sinash
Step 2 "Serverga ulanishni sinash"
$out = (& $Ssh @SshOpts "root@$IP" "echo ULANDI" 2>&1 | ForEach-Object { "$_" }) -join "`n"
if (($LASTEXITCODE -ne 0) -or ($out -notmatch "ULANDI")) {
    Say $out "DarkGray"
    Say ""
    Say "Nima qilish kerak:" "Yellow"
    Say "  'Permission denied (publickey)'  -> server SSH kalitsiz yaratilgan: serverni o'chirib, kalit bilan qayta yarating."
    Say "  'Connection timed out'           -> IP xato yozilgan yoki server hali Running emas."
    Say "  'Could not resolve hostname'     -> IP o'rniga so'z kirib qolgan."
    Say "  'HOST IDENTIFICATION HAS CHANGED'-> eski server yozuvi: PowerShell'da  ssh-keygen -R $IP  deb yozing, keyin qayta urining."
    Fail "Serverga ulanib bo'lmadi."
}
Say "Ulandi." "Green"

# ---------------------------------------------------------------- 3. Noutbukdagi agentni to'xtatish
Step 3 "Noutbukdagi agent to'xtatilmoqda (endi u serverda ishlaydi)"
Set-Location $Root
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop ochiq emas. Uni oching ('Engine running' bo'lguncha kuting) va VPSGA_JOYLASH.bat ni qayta ishga tushiring." }
& docker compose down

# ---------------------------------------------------------------- 4. Telegramga yangi kirish
Step 4 "Telegramga yangi kirish: telefon raqamingiz (+998...) va Telegramga kelgan KOD so'raladi"
Say "Kodni hech kimga va hech qaysi chatga yubormang: Telegram uni bekor qiladi." "Yellow"
$DataDir = Join-Path $Root "data"
Get-ChildItem -Path $DataDir -Filter "hunter.session*" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
& docker compose run --rm hunter python -m scripts.login
$LoginCode = $LASTEXITCODE
$SessionFile = Join-Path $DataDir "hunter.session"
if (($LoginCode -ne 0) -or (-not (Test-Path $SessionFile))) {
    Fail "Telegramga kirish bajarilmadi. Raqamni +998... ko'rinishida yozing va kodni to'g'ri kiriting, keyin VPSGA_JOYLASH.bat ni qayta ishga tushiring."
}
Say "Telegram sessiyasi tayyor." "Green"

# ---------------------------------------------------------------- 5. Serverga yuborish
Step 5 "Papka serverga yuborilmoqda"
$has = (& $Ssh @SshOpts "root@$IP" "test -f $Remote/data/hunter.db && echo BOR || echo YOQ" 2>&1 | ForEach-Object { "$_" }) -join ""
if ($has -match "BOR") {
    Fail "Serverda agent allaqachon ishlagan (baza bor). Uning ustidan yozib yubormaslik uchun to'xtadim. Yangilash kerak bo'lsa, menga ayting."
}
Remove-Item (Join-Path $DataDir "media") -Recurse -Force -ErrorAction SilentlyContinue   # vaqtinchalik media, kerak emas
$Tgz = Join-Path $Temp "tg_hunter_deploy.tgz"
Remove-Item $Tgz -Force -ErrorAction SilentlyContinue
& $Tar -czf $Tgz -C $Root .
if (($LASTEXITCODE -ne 0) -or (-not (Test-Path $Tgz))) { Fail "Papkani arxivlab bo'lmadi (tar)." }
Set-Location $Temp
& $Scp @SshOpts "tg_hunter_deploy.tgz" "root@${IP}:/root/tg_hunter_deploy.tgz"
$ScpCode = $LASTEXITCODE
Set-Location $Root
if ($ScpCode -ne 0) { Fail "Serverga yuborib bo'lmadi (scp)." }
$ex = (& $Ssh @SshOpts "root@$IP" "mkdir -p $Remote && tar -xzf /root/tg_hunter_deploy.tgz -C $Remote && rm -f /root/tg_hunter_deploy.tgz && test -f $Remote/deploy/server_install.sh && echo JOYLANDI" 2>&1 | ForEach-Object { "$_" }) -join "`n"
if ($ex -notmatch "JOYLANDI") { Fail "Serverda fayllarni ochib bo'lmadi: $ex" }
Remove-Item $Tgz -Force -ErrorAction SilentlyContinue
Say "Papka serverga yuborildi." "Green"

# ---------------------------------------------------------------- 6. Serverda o'rnatish
Step 6 "Serverda o'rnatish va tekshirish (5-15 daqiqa). Oynani yopmang, noutbuk uxlamasin."
$Log = Join-Path $Temp "tg_hunter_install.log"
& $Ssh @SshOpts "root@$IP" "bash $Remote/deploy/server_install.sh" 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log
$InstallCode = $LASTEXITCODE
if ($InstallCode -ne 0) {
    $blocked = $false
    if (Test-Path $Log) { $blocked = [bool](Select-String -Path $Log -Pattern "ISHGA TUSHIRILMADI" -Quiet) }
    if ($blocked) {
        Say ""
        Say "Tekshiruvda muammo chiqdi, agent ishga tushirilmadi." "Yellow"
        Say "Yuqoridagi xato (qizil krest) belgili qatorlarda FAQAT AI/Gemini bo'lsa (kvota), agentni baribir ishga tushirish mumkin:" "Yellow"
        Say "u DRY-RUN rejimida, kanalga hech narsa joylamaydi." "Yellow"
        $ans = (Read-Host "Baribir ishga tushiraymi? (ha/yoq)").Trim().ToLower()
        if ($ans -eq "ha") {
            & $Ssh @SshOpts "root@$IP" "FORCE=1 bash $Remote/deploy/server_install.sh" 2>&1 | ForEach-Object { "$_" }
            $InstallCode = $LASTEXITCODE
        }
    }
}
if ($InstallCode -ne 0) { Fail "O'rnatish tugallanmadi. Oxirgi qatorlarni skrinshot qilib yuboring." }
Remove-Item $Log -Force -ErrorAction SilentlyContinue

Write-Host ""
Say "==== TAYYOR ====" "Green"
Say "Bir necha soniyadan keyin @ovchitg_bot sizga 'TG Hunter ishga tushdi' deb yozadi. Unga /status yuboring (DRY-RUN yoqilgan)." "Green"
Say "Noutbukda BOSHLASH.bat ni endi bosmang: agent serverda ishlaydi." "Yellow"
exit 0
