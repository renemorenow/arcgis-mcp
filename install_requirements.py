"""
Script inteligente de instalación de dependencias.
Solo instala paquetes que NO están presentes en el entorno actual.

Además ejecuta una validación post-instalación enfocada en el runtime crítico
de arcgis-mcp para evitar reportar éxito cuando el entorno quedó inconsistente.
"""
import importlib
import re
import subprocess
import sys
from pathlib import Path
from importlib.metadata import version, requires, PackageNotFoundError


CRITICAL_RUNTIME_IMPORTS = [
    ("arcgis", "arcgis"),
    ("fastmcp", "fastmcp"),
    ("python-dotenv", "dotenv"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("starlette", "starlette"),
    ("PyJWT", "jwt"),
]

CRITICAL_PIP_TOKENS = {
    "arcgis",
    "fastmcp",
    "python-dotenv",
    "dotenv",
    "fastapi",
    "uvicorn",
    "starlette",
    "pyjwt",
    "jwt",
    "pyarrow",
}


def is_package_installed(package_name):
    """Verifica si un paquete está instalado."""
    # Normalizar nombre (quitar extras como [standard])
    base_name = package_name.split('[')[0].strip()
    
    try:
        ver = version(base_name)
        return True, ver
    except PackageNotFoundError:
        return False, None


def read_requirements(file_path='requirements.txt'):
    """Lee el archivo requirements.txt."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def format_exception(exc: Exception) -> str:
    """Reduce una excepción a una línea legible para el resumen final."""
    return f"{exc.__class__.__name__}: {exc}".strip()


def import_module_check(module_name: str):
    """Intenta importar un módulo y devuelve (ok, detalle)."""
    try:
        importlib.import_module(module_name)
        return True, "OK"
    except Exception as exc:  # pragma: no cover - depende del runtime real
        return False, format_exception(exc)


def arcgis_requires_pyarrow() -> bool:
    """Detecta si la distribución arcgis declara pyarrow como dependencia."""
    try:
        arcgis_requirements = requires('arcgis') or []
    except PackageNotFoundError:
        return False

    return any('pyarrow' in requirement.lower() for requirement in arcgis_requirements)


def run_pip_check():
    """Ejecuta pip check y clasifica problemas relevantes para este proyecto."""
    proc = subprocess.run(
        [sys.executable, '-m', 'pip', 'check'],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or '') + (proc.stderr or '')
    findings = [line.strip() for line in output.splitlines() if line.strip()]

    blockers = []
    warnings = []

    for finding in findings:
        normalized_tokens = set(re.findall(r'[a-z0-9][a-z0-9._-]*', finding.lower()))
        if normalized_tokens & CRITICAL_PIP_TOKENS:
            blockers.append(finding)
        else:
            warnings.append(finding)

    return {
        'returncode': proc.returncode,
        'blockers': blockers,
        'warnings': warnings,
        'raw_output': output.strip(),
    }


def run_post_install_health_check(requirements):
    """Valida imports críticos y revisa consistencia básica del runtime."""
    print("\n" + "=" * 70)
    print("Validación post-instalación del runtime crítico")
    print("=" * 70)

    critical_failures = []
    warnings = []

    requested_packages = {
        package.split('[')[0].strip().lower()
        for package in requirements
    }

    for distribution_name, module_name in CRITICAL_RUNTIME_IMPORTS:
        normalized_dist = distribution_name.lower()
        if normalized_dist not in requested_packages:
            continue

        ok, detail = import_module_check(module_name)
        if ok:
            print(f"✅ import {module_name}")
        else:
            print(f"❌ import {module_name} -> {detail}")
            critical_failures.append(
                f"Import crítico falló: import {module_name} -> {detail}"
            )

    arcgis_installed, arcgis_version = is_package_installed('arcgis')
    if arcgis_installed and arcgis_requires_pyarrow():
        ok, detail = import_module_check('pyarrow')
        if ok:
            print(f"✅ import pyarrow (requerido por arcgis {arcgis_version})")
        else:
            print(f"❌ import pyarrow -> {detail}")
            critical_failures.append(
                f"ArcGIS requiere pyarrow en este entorno y no se pudo importar: {detail}"
            )

    pip_check = run_pip_check()
    if pip_check['returncode'] == 0:
        print("✅ python -m pip check")
    else:
        print("⚠️  python -m pip check reportó inconsistencias")
        warnings.extend(
            f"pip check (no bloqueante): {finding}"
            for finding in pip_check['warnings']
        )
        critical_failures.extend(
            f"pip check (crítico): {finding}"
            for finding in pip_check['blockers']
        )

    print("\nResumen de validación:")
    print(f"  Fallos críticos:        {len(critical_failures)}")
    print(f"  Advertencias:           {len(warnings)}")

    if critical_failures:
        print("\nFALLOS CRÍTICOS:")
        for failure in critical_failures:
            print(f"  - {failure}")

    if warnings:
        print("\nADVERTENCIAS / NO BLOQUEANTES:")
        for warning in warnings:
            print(f"  - {warning}")

    if critical_failures:
        print("\n❌ La instalación NO es válida para arcgis-mcp.")
        print("   Corrige el runtime anterior antes de continuar.")
        return 1

    print("\n✅ Runtime crítico validado correctamente.")
    if warnings:
        print("   Hay advertencias no bloqueantes fuera del runtime crítico del proyecto.")
    return 0


def select_constraints_file(base_dir: Path):
    """Selecciona el archivo de constraints según la versión real de Python."""
    py = sys.version_info

    if py.major != 3 or py.minor < 11:
        raise RuntimeError(
            f"Python {py.major}.{py.minor} no es compatible con MCP. Se requiere 3.11+"
        )

    if py.minor == 11:
        name = 'constraints-py311.txt'
    elif py.minor == 12:
        name = 'constraints-py312.txt'
    else:
        name = 'constraints-py313plus.txt'

    path = base_dir / name
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de constraints: {path}")

    return path


def main():
    base_dir = Path(__file__).resolve().parent

    print("=" * 70)
    print("Verificación e instalación inteligente de dependencias")
    print("=" * 70)
    print(f"Python: {sys.executable}")
    print(f"Versión: {sys.version.split()[0]}")
    constraints_file = select_constraints_file(base_dir)
    print(f"Constraints: {constraints_file.name}")
    print()
    
    requirements = read_requirements(base_dir / 'requirements.txt')
    
    installed = []
    missing = []
    
    # Verificar cada paquete
    print("Verificando paquetes...")
    print("-" * 70)
    
    for package in requirements:
        is_installed, ver = is_package_installed(package)
        
        if is_installed:
            installed.append((package, ver))
            print(f"✅ {package:30} → Ya instalado (v{ver})")
        else:
            missing.append(package)
            print(f"❌ {package:30} → NO encontrado")
    
    print("-" * 70)
    print(f"\nResumen:")
    print(f"  ✅ Ya instalados: {len(installed)}")
    print(f"  ❌ Faltantes:     {len(missing)}")
    print()
    
    # Instalar solo los faltantes
    if missing:
        print("Instalando paquetes faltantes...")
        print("-" * 70)
        
        for package in missing:
            print(f"\nInstalando: {package}")
            try:
                subprocess.check_call([
                    sys.executable, 
                    '-m', 
                    'pip', 
                    'install', 
                    package,
                    '-c',
                    str(constraints_file),
                    '--quiet'
                ])
                print(f"  ✅ {package} instalado correctamente")
            except subprocess.CalledProcessError as e:
                print(f"  ❌ Error instalando {package}: {e}")
                return 1
        
        print("-" * 70)
        print("\n✅ Todas las dependencias faltantes han sido instaladas.")
    else:
        print("✅ Todas las dependencias ya están instaladas. No hay nada que hacer.")
    
    health_status = run_post_install_health_check(requirements)
    if health_status != 0:
        return health_status

    print("\n" + "=" * 70)
    print("Instalación completada exitosamente.")
    print("=" * 70)

    return 0


if __name__ == '__main__':
    sys.exit(main())
