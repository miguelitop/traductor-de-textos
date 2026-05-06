#!/bin/bash
# setup-ollama-perf.sh
# Setea variables de optimización y reinicia Ollama.
set -euo pipefail

echo "==> Seteando variables via launchctl..."
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m

echo "==> Variables seteadas:"
launchctl getenv OLLAMA_FLASH_ATTENTION
launchctl getenv OLLAMA_KV_CACHE_TYPE
launchctl getenv OLLAMA_KEEP_ALIVE

echo "==> Reiniciando Ollama..."
if pgrep -x "Ollama" > /dev/null; then
    # App de la barra de menú
    echo "    Detectada Ollama.app, cerrando y reabriendo..."
    osascript -e 'tell application "Ollama" to quit' 2>/dev/null || true
    sleep 2
    pkill -x ollama 2>/dev/null || true
    sleep 1
    open -a Ollama
elif brew services list 2>/dev/null | grep -q "^ollama.*started"; then
    # Homebrew service
    echo "    Detectado brew service, reiniciando..."
    brew services restart ollama
else
    # ollama serve manual o daemon genérico
    echo "    Matando proceso ollama y reiniciando..."
    pkill ollama 2>/dev/null || true
    sleep 1
    nohup ollama serve > /tmp/ollama.log 2>&1 &
fi

echo "==> Esperando que el server responda..."
for i in {1..15}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "    Ollama responde."
        break
    fi
    sleep 1
done

echo ""
echo "==> Listo. Para verificar que Flash Attention se aplicó, hacé"
echo "    una traducción y luego revisá el log:"
echo "    grep flash_attention ~/.ollama/logs/server.log | tail -5"
