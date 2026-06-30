# Protocolo de Comunicação

## Visão geral

A comunicação entre o ESP32 e o desktop usa **TCP puro com mensagens JSON**.

- **Camada de transporte:** TCP/IP (socket stream)
- **Codificação:** UTF-8
- **Framing:** cada mensagem é uma única linha JSON terminada com `\n` (newline)
- **Direção:** bidirecional
- **Papel dos lados:**
  - **ESP32 → servidor TCP** (bind + listen + accept na porta 8080)
  - **Desktop → cliente TCP** (connect)

Não há cabeçalho de comprimento nem estado de sessão além da conexão TCP ativa. Cada linha recebida é um JSON independente e auto-contido.

---

## Campo `type`

Todas as mensagens contêm um campo `"type"` que identifica o propósito:

| `type` | Direção | Descrição |
|---|---|---|
| `"reading"` | ESP32 → Desktop | Leitura periódica do sensor + estado do sistema |
| `"config"` | Desktop → ESP32 | Novos limiares de operação |
| `"ack"` | ESP32 → Desktop | Confirmação ou erro após receber um `config` |

---

## Mensagens

### `reading` — Leitura e estado

Enviada pelo ESP32 a cada 2,5 segundos (ou imediatamente após mudança de estado).

```json
{
  "type":  "reading",
  "seq":   42,
  "temp":  24.5,
  "hum":   67.3,
  "heat":  false,
  "dehum": true,
  "rec":   "Ambiente quente e umido. Ventilar por 15-30 min."
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `seq` | `uint` | Contador monotonicamente crescente; incrementado a cada atualização de estado |
| `temp` | `float` | Temperatura em °C (1 casa decimal) |
| `hum` | `float` | Umidade relativa em % (1 casa decimal) |
| `heat` | `bool` | `true` se o LED de aquecimento está ativo |
| `dehum` | `bool` | `true` se o LED de desumidificação está ativo |
| `rec` | `string` | Recomendação textual de ventilação natural |

---

### `config` — Configuração de limiares

Enviada pelo desktop para atualizar os limiares operacionais do ESP32.

```json
{
  "type":        "config",
  "temp_thresh": 18.0,
  "hum_thresh":  55.0
}
```

| Campo | Tipo | Restrições |
|---|---|---|
| `temp_thresh` | `float` | −10 a 50 °C |
| `hum_thresh` | `float` | 0 a 100 % |

Valores fora das restrições serão rejeitados com uma resposta `ack` de erro.

---

### `ack` — Confirmação

Enviada pelo ESP32 após processar uma mensagem `config`.

**Sucesso:**
```json
{
  "type":   "ack",
  "status": "ok"
}
```

**Erro (valor inválido):**
```json
{
  "type":   "ack",
  "status": "error",
  "msg":    "Invalid or out-of-range values"
}
```

| Campo | Tipo | Valores possíveis |
|---|---|---|
| `status` | `string` | `"ok"` ou `"error"` |
| `msg` | `string` | Presente apenas quando `status = "error"` |

---

## Exemplo de sessão completa

```
[ESP32 → Desktop]
{"type":"reading","seq":1,"temp":24.5,"hum":67.3,"heat":false,"dehum":true,"rec":"Ambiente quente e umido. Ventilar por 15-30 min."}\n

[ESP32 → Desktop]
{"type":"reading","seq":2,"temp":24.4,"hum":67.5,"heat":false,"dehum":true,"rec":"Ambiente quente e umido. Ventilar por 15-30 min."}\n

[Desktop → ESP32]
{"type":"config","temp_thresh":18.0,"hum_thresh":55.0}\n

[ESP32 → Desktop]
{"type":"ack","status":"ok"}\n

[ESP32 → Desktop]
{"type":"reading","seq":3,"temp":24.4,"hum":67.5,"heat":false,"dehum":true,"rec":"Ambiente quente e umido. Ventilar por 15-30 min."}\n
```

---

## Comportamento de reconexão

- O ESP32 aceita uma conexão por vez. Quando o desktop desconecta, o servidor volta a aguardar uma nova conexão.
- O desktop tenta reconectar automaticamente a cada 3 segundos em caso de falha.
- Não há mecanismo de autenticação ou criptografia — o sistema opera em rede local confiável.

---

## Recomendação de ventilação

A string `rec` é gerada pelo firmware com base na combinação dos estados `heat` e `dehum`:

| Condição | Recomendação |
|---|---|
| Nenhum ativo | "Condicoes adequadas. Ventilacao opcional." |
| Só `dehum` ativo | "Ambiente quente e umido. Ventilar por 15-30 min." |
| Só `heat` ativo | "Temperatura baixa. Evite ventilacao prolongada." |
| Ambos ativos | "Frio e umido. Ventilar brevemente (5-10 min) e depois fechar." |

A lógica é coerente com o objetivo de reduzir umidade sem piorar excessivamente o conforto térmico.
