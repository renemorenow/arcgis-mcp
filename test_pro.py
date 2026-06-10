"""
Script de prueba para conexión con ArcGIS Pro activo.
Verifica que el usuario esté autenticado en Pro.

Requisitos:
- ArcGIS Pro debe estar abierto
- El usuario debe haber iniciado sesión en Pro

Uso:
    python test_pro.py
"""
import sys
from arcgis.gis import GIS


def test_pro_connection():
    """Prueba conexión con sesión activa de ArcGIS Pro."""
    print("=" * 70)
    print("Prueba de Conexión con ArcGIS Pro")
    print("=" * 70)
    print()
    print("Verificando sesión activa de ArcGIS Pro...")
    print("-" * 70)
    
    try:
        # Intentar conexión con Pro
        gis = GIS("Pro")
        
        if gis is None:
            print("❌ No se pudo obtener instancia de GIS")
            return 1
        
        print("\n✅ Conexión exitosa con ArcGIS Pro!")
        print("-" * 70)
        
        # Información del usuario
        me = gis.users.me
        if me:
            print(f"Usuario: {me.username}")
            print(f"Nombre completo: {me.fullName}")
            print(f"Email: {me.email}")
            print(f"Rol: {me.role}")
        else:
            print("⚠️  No se pudo obtener información del usuario")
        
        # Información del portal
        props = gis.properties
        print(f"\nOrganización: {props.get('name', 'N/A')}")
        print(f"Portal: {gis.url}")
        print(f"Versión: {props.get('currentVersion', 'N/A')}")
        
        # Detectar si es Portal o ArcGIS Online
        is_portal = props.get("isPortal", False)
        platform = "ArcGIS Enterprise (Portal)" if is_portal else "ArcGIS Online"
        print(f"Plataforma: {platform}")
        
        # Privilegios
        if me and hasattr(me, 'privileges'):
            privs = me.privileges or []
            print(f"\nPrivilegios: {len(privs)} disponibles")
            if privs:
                print("Ejemplos:")
                for priv in privs[:5]:
                    print(f"  - {priv}")
                if len(privs) > 5:
                    print(f"  ... y {len(privs) - 5} más")
        
        print("\n" + "=" * 70)
        print("✅ La sesión de ArcGIS Pro está activa y funcional.")
        print("\nEl servidor MCP detectará automáticamente esta sesión.")
        print("No necesitas configurar .env si usas este modo.")
        print("=" * 70)
        
        return 0
    
    except RuntimeError as e:
        error_msg = str(e)
        print(f"\n❌ Error de conexión con ArcGIS Pro:")
        print(f"   {error_msg}")
        print("\nPosibles causas:")
        if "not licensed" in error_msg.lower() or "license" in error_msg.lower():
            print("  - ArcGIS Pro no tiene licencia válida")
            print("  - La licencia de Pro ha expirado")
        elif "not signed in" in error_msg.lower() or "sign in" in error_msg.lower():
            print("  - No has iniciado sesión en ArcGIS Pro")
            print("  - Abre Pro y conéctate a tu portal primero")
        elif "not running" in error_msg.lower() or "not found" in error_msg.lower():
            print("  - ArcGIS Pro no está abierto")
            print("  - Abre ArcGIS Pro antes de ejecutar este script")
        else:
            print("  - ArcGIS Pro no está instalado correctamente")
            print("  - El entorno Python no es el de ArcGIS Pro")
            print("  - ArcGIS Pro está abierto pero no conectado")
        
        print("\nSolución:")
        print("  1. Abre ArcGIS Pro")
        print("  2. Haz clic en 'Sign In' y conéctate a tu portal")
        print("  3. Ejecuta este script nuevamente")
        print("\nAlternativas:")
        print("  - Usa OAuth2: ARCGIS_USE_OAUTH=true en .env")
        print("  - Usa perfil: ARCGIS_PROFILE=nombre_perfil en .env")
        print("  - Usa credenciales en .env")
        return 1
    
    except Exception as e:
        print(f"\n❌ Error inesperado:")
        print(f"   {e}")
        print("\nVerifica:")
        print("  - Estás ejecutando esto desde el entorno conda de ArcGIS Pro")
        print("  - ArcGIS Pro está instalado correctamente")
        return 1


if __name__ == '__main__':
    sys.exit(test_pro_connection())
