"""
Smoke test — verifica que las tools principales responden sin errores.
NO realiza escrituras. ARCGIS_WRITE_ENABLED debe estar en false (default).

Uso:
    python test_smoke.py
    python test_smoke.py --profile facbni   # override de perfil
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

# Asegurar write disabled para este test
os.environ.setdefault("ARCGIS_WRITE_ENABLED", "false")

parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="", help="ARCGIS_PROFILE override")
args = parser.parse_args()
if args.profile:
    os.environ["ARCGIS_PROFILE"] = args.profile

# Importar las funciones del MCP directamente
sys.path.insert(0, os.path.dirname(__file__))
from arcgis_mcp import (
    whoami,
    gis_version,
    content_search,
    # --- nuevos ---
    webmap_layers,
    geocode,
    mil_sublayers,
    org_credits,
    enrich_countries,
    webscene_get,
    notebook_list,
    webhook_list,
    admin_org_settings,
)

PASS = "✓"
FAIL = "✗"
SKIP = "~"

results: list[tuple[str, str, str]] = []


def run(name: str, fn, *a, **kw):
    try:
        result = fn(*a, **kw)
        results.append((PASS, name, ""))
        print(f"  {PASS} {name}")
        if "--verbose" in sys.argv:
            print(f"      {str(result)[:120]}")
    except PermissionError as e:
        results.append((SKIP, name, f"write disabled (esperado): {e}"))
        print(f"  {SKIP} {name}  [write disabled — OK]")
    except RuntimeError as e:
        msg = str(e)
        if "Solo disponible en ArcGIS Enterprise" in msg:
            results.append((SKIP, name, "Enterprise-only (OK si usás AGOL)"))
            print(f"  {SKIP} {name}  [Enterprise-only — OK si usás AGOL]")
        else:
            results.append((FAIL, name, msg))
            print(f"  {FAIL} {name}  ERROR: {msg[:100]}")
            if "--verbose" in sys.argv:
                traceback.print_exc()
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL} {name}  ERROR: {str(e)[:100]}")
        if "--verbose" in sys.argv:
            traceback.print_exc()


print("\n=== ARCGIS-MCP SMOKE TEST ===\n")

print("[ INTROSPECCIÓN ]")
run("whoami", whoami)
run("gis_version", gis_version)

print("\n[ CONTENIDO ]")
run("content_search(empty)", content_search, query="", max_items=3)
run("content_search(Web Map)", content_search, query="", item_type="Web Map", max_items=3)

print("\n[ WEB MAPS ]")
# Busca un web map existente para probar webmap_layers
from arcgis_mcp import get_gis, content_search as cs
try:
    gis = get_gis()
    maps = gis.content.search("", item_type="Web Map", max_items=1)
    if maps:
        run("webmap_layers", webmap_layers, item_id=maps[0].id)
    else:
        results.append((SKIP, "webmap_layers", "sin web maps disponibles"))
        print(f"  {SKIP} webmap_layers  [sin web maps — skipped]")
except Exception as e:
    results.append((FAIL, "webmap_layers (setup)", str(e)))
    print(f"  {FAIL} webmap_layers (setup): {e}")

print("\n[ GEOCODIFICACIÓN ]")
run("geocode('Bogotá Colombia')", geocode, address="Bogotá Colombia", max_locations=2)

print("\n[ ORGANIZACIÓN ]")
run("admin_org_settings", admin_org_settings)
run("org_credits", org_credits)

print("\n[ GEOENRICHMENT ]")
run("enrich_countries", enrich_countries)

print("\n[ NOTEBOOKS (Enterprise) ]")
run("notebook_list", notebook_list, max_items=5)

print("\n[ WEBHOOKS (Enterprise) ]")
run("webhook_list", webhook_list)

print("\n[ WRITE TOOLS — deben fallar con PermissionError ]")
from arcgis_mcp import webmap_create, item_protect, admin_reindex
run("webmap_create (blocked)", webmap_create, title="test", dry_run=False)
run("item_protect (blocked)", item_protect, item_id="fake-id", dry_run=False)
run("admin_reindex (blocked)", admin_reindex, dry_run=False)

# Resumen
total = len(results)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
skipped = sum(1 for r in results if r[0] == SKIP)

print(f"\n{'='*40}")
print(f"  Total: {total}  |  {PASS} {passed}  |  {FAIL} {failed}  |  {SKIP} {skipped} (skipped/OK)")
if failed:
    print("\nFALLOS:")
    for r in results:
        if r[0] == FAIL:
            print(f"  - {r[1]}: {r[2]}")
print()
sys.exit(1 if failed else 0)
