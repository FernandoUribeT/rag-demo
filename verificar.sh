#!/usr/bin/env bash
# Verificación de extremo a extremo contra un servidor corriendo.
#
# Las pruebas automatizadas cubren la lógica; esto cubre lo que ellas no pueden:
# que el sistema real, con Stripe real, se comporte como se espera.
#
#   ./verificar.sh
#
# Requiere, en otras terminales:
#   1) uvicorn rag_demo.servidor:app
#   2) stripe listen --forward-to localhost:8000/api/webhooks/stripe

set -uo pipefail

API="${API:-http://localhost:8000}"
CLIENTE="verificacion-$$"        # cliente distinto en cada corrida
H=(-H "Content-Type: application/json" -H "X-Cliente: $CLIENTE")

ok=0; fallos=0

comprobar() {
    local descripcion="$1" esperado="$2" obtenido="$3"
    if [ "$esperado" = "$obtenido" ]; then
        printf '  \033[32m✓\033[0m %s\n' "$descripcion"
        ok=$((ok + 1))
    else
        printf '  \033[31m✗\033[0m %s — esperaba «%s», obtuvo «%s»\n' \
            "$descripcion" "$esperado" "$obtenido"
        fallos=$((fallos + 1))
    fi
}

echo "Verificando contra $API con el cliente $CLIENTE"
echo

# ── Lo que se puede comprobar sin pagar ──────────────────────────────────────
echo "Sin pago:"

comprobar "el servicio responde" "ok" \
    "$(curl -s "$API/api/salud" -H "X-Cliente: $CLIENTE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["estado"])' 2>/dev/null)"

comprobar "un cliente nuevo arranca sin créditos" "0" \
    "$(curl -s "$API/api/saldo" -H "X-Cliente: $CLIENTE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["creditos"])' 2>/dev/null)"

comprobar "sin saldo no se puede indexar" "402" \
    "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/documentos" "${H[@]}" \
        -d '{"nombre":"x","contenido":"texto"}')"

comprobar "un webhook con firma inválida se rechaza" "400" \
    "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/webhooks/stripe" \
        -H 'Stripe-Signature: invalida' -d '{"type":"checkout.session.completed"}')"

comprobar "un paquete inventado se rechaza" "422" \
    "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/checkout" "${H[@]}" \
        -d '{"paquete":"gratis"}')"

echo
echo "Pago:"

URL=$(curl -s -X POST "$API/api/checkout" "${H[@]}" -d '{"paquete":"creditos_10"}' \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("url",""))' 2>/dev/null)

if [ -z "$URL" ]; then
    printf '  \033[31m✗\033[0m no se pudo crear la sesión de pago\n'
    fallos=$((fallos + 1))
else
    printf '  \033[32m✓\033[0m sesión de pago creada\n'
    ok=$((ok + 1))
    echo
    echo "  Abre esta URL y paga con la tarjeta de prueba 4242 4242 4242 4242:"
    echo "  $URL"
    echo
    echo "  El cliente de esta corrida es: $CLIENTE"
    echo "  Al terminar, comprueba el saldo (debe ser 10):"
    echo "    curl -s $API/api/saldo -H 'X-Cliente: $CLIENTE'"
    echo
    echo "  Y reenvía el evento desde el panel para comprobar la idempotencia:"
    echo "    el saldo debe SEGUIR en 10, no subir a 20."
fi

echo
echo "─────────────────────────────────────────"
printf 'Automáticas: %d correctas, %d fallidas\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
