"""
Script de prueba para autenticación OAuth2 interactiva.
Abre el navegador para que el usuario se autentique.

Uso:
    python test_oauth.py
    python test_oauth.py --url https://mi-portal.com/portal
    python test_oauth.py --url https://mi-portal.com/portal --client-id mi_app_id
"""
import sys
from arcgis.gis import GIS


def test_oauth(url="https://www.arcgis.com", client_id="arcgisonline"):
    """Prueba autenticación OAuth2."""
    print("=" * 70)
    print("Prueba de Autenticación OAuth2 - ArcGIS")
    print("=" * 70)
    print(f"URL: {url}")
    print(f"Client ID: {client_id}")
    print()
    print("Se abrirá el navegador para que ingreses tus credenciales...")
    print("Sigue las instrucciones en el navegador.")
    print("-" * 70)
    
    try:
        # Autenticación OAuth2 - abre el navegador
        gis = GIS(url, client_id=client_id)
        
        print("\n✅ Autenticación exitosa!")
        print("-" * 70)
        print(f"Usuario: {gis.users.me.username}")
        print(f"Nombre completo: {gis.users.me.fullName}")
        print(f"Email: {gis.users.me.email}")
        print(f"Rol: {gis.users.me.role}")
        print(f"Organización: {gis.properties.get('name', 'N/A')}")
        print(f"Portal: {gis.url}")
        print(f"Versión: {gis.version}")
        
        # Evita exponer fragmentos del token en salida de consola
        if gis._con.token:
            print("\nToken generado correctamente.")
        
        print("\n" + "=" * 70)
        print("✅ OAuth2 funciona correctamente.")
        print("\nPara usar este modo en el servidor MCP, configura:")
        print("  ARCGIS_USE_OAUTH=true")
        print(f"  ARCGIS_URL={url}")
        if client_id != "arcgisonline":
            print(f"  ARCGIS_CLIENT_ID={client_id}")
        print("=" * 70)
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Error en autenticación OAuth2:")
        print(f"   {e}")
        print("\nPosibles causas:")
        print("  - No se pudo abrir el navegador")
        print("  - El usuario canceló la autenticación")
        print("  - El client_id no es válido")
        print("  - Problemas de red")
        return 1


if __name__ == '__main__':
    # Parsear argumentos simples
    url = "https://www.arcgis.com"
    client_id = "arcgisonline"
    
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        if idx + 1 < len(sys.argv):
            url = sys.argv[idx + 1]
    
    if "--client-id" in sys.argv:
        idx = sys.argv.index("--client-id")
        if idx + 1 < len(sys.argv):
            client_id = sys.argv[idx + 1]
    
    sys.exit(test_oauth(url, client_id))
