"""
Script de verificación post-instalación para ArcGIS MCP.
Verifica que todas las dependencias estén correctamente instaladas y funcionales.
"""
import sys
from importlib.metadata import version, PackageNotFoundError


def check_package(package_name, module_name=None):
    """Verifica que un paquete esté instalado y se pueda importar."""
    if module_name is None:
        module_name = package_name
    
    # Verificar instalación
    try:
        ver = version(package_name)
        installed = True
    except PackageNotFoundError:
        installed = False
        ver = "N/A"
    
    # Verificar importación
    if installed:
        try:
            __import__(module_name)
            importable = True
            error = None
        except Exception as e:
            importable = False
            error = str(e)
    else:
        importable = False
        error = "Paquete no instalado"
    
    return installed, ver, importable, error


def check_arcgis_connection():
    """Intenta conectarse a ArcGIS para verificar configuración."""
    try:
        from arcgis.gis import GIS
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        # Intentar conexión Pro
        try:
            print("   [INFO] Intentando conexión con ArcGIS Pro...", end="")
            gis = GIS("Pro")
            if gis is not None:
                username = gis.users.me.username if gis.users.me else "usuario Pro"
                print(" OK")
                return True, "Pro", f"{username} - {gis.properties.get('name', 'N/A')}"
        except Exception as e:
            print(f" No disponible ({str(e)[:50]}...)")
        
        # Verificar si OAuth2 está configurado
        use_oauth = os.environ.get("ARCGIS_USE_OAUTH", "false").lower() == "true"
        if use_oauth:
            print("   [INFO] OAuth2 configurado (requiere navegador al ejecutar)")
            return True, "OAuth2 (configurado)", "Requiere ejecución interactiva"
        
        # Verificar perfil
        profile = os.environ.get("ARCGIS_PROFILE")
        if profile:
            try:
                print(f"   [INFO] Intentando conexión con perfil: {profile}...", end="")
                gis = GIS(profile=profile)
                username = gis.users.me.username if gis.users.me else "usuario perfil"
                print(" OK")
                return True, f"Perfil ({profile})", f"{username} - {gis.properties.get('name', 'N/A')}"
            except Exception as e:
                print(f" Error: {str(e)[:50]}...")
                return False, f"Perfil ({profile})", f"Error: {str(e)}"
        
        # Intentar con .env (URL/User/Pass, API Key, Token)
        url = os.environ.get("ARCGIS_URL")
        user = os.environ.get("ARCGIS_USER")
        password = os.environ.get("ARCGIS_PASS")
        api_key = os.environ.get("ARCGIS_API_KEY")
        token = os.environ.get("ARCGIS_TOKEN")
        
        if url and api_key:
            try:
                print(f"   [INFO] Intentando conexión con API Key a {url}...", end="")
                gis = GIS(url, api_key=api_key)
                print(" OK")
                return True, "API Key", gis.properties.get("name", "N/A")
            except Exception as e:
                print(f" Error: {str(e)[:50]}...")
                return False, "API Key", f"Error: {str(e)}"
        
        if url and token:
            try:
                print(f"   [INFO] Intentando conexión con Token a {url}...", end="")
                gis = GIS(url, token=token)
                print(" OK")
                return True, "Token", gis.properties.get("name", "N/A")
            except Exception as e:
                print(f" Error: {str(e)[:50]}...")
                return False, "Token", f"Error: {str(e)}"
        
        if url and user and password:
            try:
                print(f"   [INFO] Intentando conexión como {user} a {url}...", end="")
                gis = GIS(url, user, password)
                print(" OK")
                return True, "URL/User/Pass", f"{user} - {gis.properties.get('name', 'N/A')}"
            except Exception as e:
                print(f" Error: {str(e)[:50]}...")
                return False, "URL/User/Pass", f"Error: {str(e)}"
        
        return False, None, "No se encontró ninguna configuración válida (.env no configurado y Pro no activo)"
    
    except Exception as e:
        return False, None, f"Error general: {str(e)}"


def main():
    print("=" * 70)
    print("Verificación Post-Instalación - ArcGIS MCP")
    print("=" * 70)
    print(f"Python: {sys.executable}")
    print(f"Versión: {sys.version.split()[0]}")
    print()
    
    # Paquetes requeridos
    packages = [
        ("arcgis", "arcgis"),
        ("fastmcp", "fastmcp"),
        ("python-dotenv", "dotenv"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
    ]
    
    print("Verificando paquetes requeridos...")
    print("-" * 70)
    
    all_ok = True
    results = []
    
    for pkg_name, module_name in packages:
        installed, ver, importable, error = check_package(pkg_name, module_name)
        results.append((pkg_name, installed, ver, importable, error))
        
        if installed and importable:
            print(f"✅ {pkg_name:20} v{ver:15} → OK")
        elif installed and not importable:
            print(f"⚠️  {pkg_name:20} v{ver:15} → Instalado pero NO se puede importar")
            print(f"   Error: {error}")
            all_ok = False
        else:
            print(f"❌ {pkg_name:20} {'':15} → NO instalado")
            all_ok = False
    
    print("-" * 70)
    
    # Verificar conexión a ArcGIS
    print("\nVerificando conexión a ArcGIS...")
    print("-" * 70)
    
    connected, method, org_name = check_arcgis_connection()
    
    if connected:
        print(f"✅ Conexión exitosa")
        print(f"   Método: {method}")
        print(f"   Organización: {org_name}")
    else:
        print(f"⚠️  No se pudo conectar a ArcGIS")
        print(f"   Razón: {org_name}")
        print(f"   Nota: Esto no impide que el servidor MCP funcione,")
        print(f"         pero necesitarás configurar credenciales antes de usarlo.")
    
    print("-" * 70)
    
    # Resumen final
    print("\nResumen:")
    installed_count = sum(1 for _, installed, _, _, _ in results if installed)
    importable_count = sum(1 for _, installed, _, importable, _ in results if installed and importable)
    
    print(f"  Paquetes instalados: {installed_count}/{len(packages)}")
    print(f"  Paquetes funcionales: {importable_count}/{len(packages)}")
    print(f"  Conexión ArcGIS: {'OK' if connected else 'No configurada'}")
    print()
    
    if all_ok:
        print("✅ VERIFICACIÓN EXITOSA - Todos los paquetes están correctamente instalados.")
        print("\nPróximos pasos:")
        print("  1. Ejecutar: python arcgis_mcp.py")
        print("  2. O en modo HTTP: python arcgis_mcp.py --http")
        return 0
    else:
        print("❌ VERIFICACIÓN FALLIDA - Algunos paquetes tienen problemas.")
        print("\nSolución:")
        print("  Ejecutar: python install_requirements.py")
        return 1
    
    print("=" * 70)


if __name__ == '__main__':
    sys.exit(main())
