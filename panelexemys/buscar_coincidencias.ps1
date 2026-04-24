param (
    [string]$Clave
)

# Si no se pasó parámetro, mostrar ayuda y salir
if (-not $Clave) {
    Write-Host ""
    Write-Host "Uso: .\buscar_coincidencias.ps1 <palabra_clave>"
    Write-Host "Busca dentro de todos los archivos .py y de forma recursva"
    Write-Host "Desde la carpeta actual. Excluye __pycache__ y venv."
    Write-Host ""
    Write-Host "Ejemplo:"
    Write-Host "    .\buscar_coincidencias.ps1 requests"
    Write-Host ""
    exit
}

# Búsqueda recursiva de la clave en .py, excluyendo __pycache__ y venv
Get-ChildItem -Recurse -Include *.py -File |
    Where-Object { $_.FullName -notmatch '\\__pycache__\\' -and $_.FullName -notmatch '\\venv\\' } |
    Select-String -Pattern $Clave -CaseSensitive:$false |
    Select-Object -Unique Path