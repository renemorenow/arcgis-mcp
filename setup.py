"""
Script maestro de setup completo para ArcGIS MCP.
Ejecuta instalación inteligente + verificación post-instalación.
"""
import subprocess
import sys


def run_script(script_name, description):
    """Ejecuta un script Python y retorna el código de salida."""
    print("\n" + "=" * 70)
    print(f"{description}")
    print("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            check=False,
            capture_output=False
        )
        return result.returncode
    except Exception as e:
        print(f"❌ Error ejecutando {script_name}: {e}")
        return 1


def main():
    print("=" * 70)
    print("SETUP COMPLETO - ArcGIS MCP")
    print("=" * 70)
    print("Este script realizará:")
    print("  1. Instalación inteligente de dependencias")
    print("  2. Verificación post-instalación")
    print("=" * 70)
    input("\nPresiona ENTER para continuar...")
    
    # Paso 1: Instalar dependencias
    exit_code = run_script("install_requirements.py", "PASO 1: Instalación de dependencias")
    
    if exit_code != 0:
        print("\n❌ La instalación falló. Abortando setup.")
        return exit_code
    
    # Paso 2: Verificar instalación
    exit_code = run_script("verify_installation.py", "PASO 2: Verificación post-instalación")
    
    if exit_code != 0:
        print("\n⚠️  La verificación detectó problemas.")
        return exit_code
    
    # Resumen final
    print("\n" + "=" * 70)
    print("🎉 SETUP COMPLETADO EXITOSAMENTE")
    print("=" * 70)
    print("\n✅ El servidor ArcGIS MCP está listo para usar.")
    print("\nOpciones de ejecución:")
    print("  1. Modo MCP (servidor):  python arcgis_mcp.py")
    print("  2. Modo HTTP (FastAPI):  python arcgis_mcp.py --http")
    print("\nDocumentación:")
    print("  README.md - Guía completa de uso")
    print("  .env.example - Ejemplo de configuración")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
