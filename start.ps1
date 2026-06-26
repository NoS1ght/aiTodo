# TaskTodo 一键启动
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "C:\Users\MECHREVO\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
Start-Process -FilePath $py -ArgumentList "$root\launcher.py" -WorkingDirectory $root
