"""Instancia compartida del servidor FastMCP.

Todos los módulos de tools importan `mcp` desde aquí para registrar
sus herramientas con @mcp.tool().
"""
from fastmcp import FastMCP

mcp = FastMCP("arcgis-mcp")
