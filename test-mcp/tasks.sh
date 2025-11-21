#!/bin/bash

echo "=== 1. Prueba Básica (Razonamiento Automático) ==="
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"tasks": ["Dame un analisis fundamental y tecnico de BTC y ETH"]}'
echo -e "\n\n"

echo "=== 2. Prueba con Herramienta Canvas ==="
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["Creame un diagrama de flujo de como funciona la libreria FastMCP"],
    "tool": "canvas"
  }'
echo -e "\n\n"

echo "=== 3. Prueba con Deep Research (Confirmación Automática) ==="
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["Investiga las mejores herramientas docker para trading de criptomonedas especificamente BTC y ETH"],
    "tool": "deep_research"
  }'
echo -e "\n\n"
