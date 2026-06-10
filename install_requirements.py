"""
Script inteligente de instalación de dependencias.
Solo instala paquetes que NO están presentes en el entorno actual.
"""
import subprocess
import sys
from importlib.metadata import version, PackageNotFoundError


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
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def main():
    print("=" * 70)
    print("Verificación e instalación inteligente de dependencias")
    print("=" * 70)
    print(f"Python: {sys.executable}")
    print(f"Versión: {sys.version.split()[0]}")
    print()
    
    requirements = read_requirements()
    
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
    
    print("\n" + "=" * 70)
    print("Instalación completada exitosamente.")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())