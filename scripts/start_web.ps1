param(
    [string]$Workdir = ".",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

python -m mmdev.cli web --workdir $Workdir --host $HostAddress --port $Port
