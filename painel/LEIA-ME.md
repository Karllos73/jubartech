# Painel do Eco-Moedor Cerâmico (tablet + ESP32)

Painel de operação para apresentar o protótipo. O tablet mostra o Eco-Moedor animado e, embaixo, uma botoeira tipo CLP com **Partida**, **Desligar** e **Emergência**. Cada botão move a máquina na tela e toca o som correspondente na caixinha Bluetooth.

## Como funciona

```
Botões físicos (opcional) ─┐
                           ├─ ESP32 ──(Bluetooth BLE)── Tablet (Chrome) ──(Bluetooth áudio)── Caixinha de som
LEDs do sinaleiro físico ◄─┘
```

- **Tablet**: roda o painel no Google Chrome. Os botões da tela funcionam sozinhos, mesmo sem a ESP32.
- **ESP32**: se tiver botões físicos ligados, eles comandam o painel. Ela também recebe o estado da máquina e acende LEDs (verde, amarelo e vermelho) no protótipo real.
- **Som**: é gerado pelo próprio painel e sai pela caixinha que está pareada no tablet. Não precisa ligar a caixinha na ESP32.

| Botão | Na tela | Som |
|---|---|---|
| Partida (I) | motor acelera, rotores giram, tijolos entram e o chamote sai na esteira | contator + motor ligando e funcionando |
| Desligar (O) | máquina desacelera até parar | motor desligando |
| Emergência | parada imediata, faixa vermelha, sinaleiro piscando | freio + sirene de alerta |

Depois da emergência, toque de novo no botão de emergência para **rearmar** (como girar o cogumelo). Enquanto ela estiver acionada, a partida fica bloqueada. O botão "Silenciar alarme" desliga a sirene sem rearmar.

## Usar no tablet (Android)

1. Pareie a caixinha de som Bluetooth no tablet (Configurações > Bluetooth) e deixe o volume alto.
2. Ligue a ESP32 com o código desta pasta.
3. No **Google Chrome**, abra o endereço do site seguido de `/painel/` (ex.: `https://SEU-SITE.vercel.app/painel/`). Precisa ser `https`, senão o Chrome bloqueia o Bluetooth.
4. Toque em **Toque para iniciar** (libera o som e coloca em tela cheia).
5. Toque em **Conectar** e escolha **Jubartech-EcoMoedor** na lista.
6. Opcional: menu do Chrome > **Adicionar à tela inicial**. Vira um app com ícone, abre em tela cheia e funciona sem internet depois da primeira vez.

Dicas: a localização e o Bluetooth do tablet precisam estar ligados para o Chrome achar a ESP32. Se a conexão cair, o painel tenta reconectar sozinho. No computador, dá para testar com o teclado: `I` partida, `O` desligar, `E` emergência.

## Gravar a ESP32

1. Arduino IDE > Gerenciador de Placas > instale **esp32 by Espressif Systems**.
2. Abra `esp32/painel_eco_moedor/painel_eco_moedor.ino`, escolha a placa (ex.: *ESP32 Dev Module*) e a porta, e grave.
3. No Monitor Serial (115200) aparece o que a ESP32 envia e recebe. Dá para testar sem botões digitando `START`, `STOP`, `EMERG` ou `EMERG_OFF`.

### Ligações padrão (mudam no topo do código)

| Função | Pino | Ligação |
|---|---|---|
| Botão Partida | GPIO 25 | botão entre o pino e o GND |
| Botão Desligar | GPIO 26 | botão entre o pino e o GND |
| Botão Emergência | GPIO 27 | botão entre o pino e o GND (NA). Para contato NF, use `EMERGENCIA_NF true` |
| LED verde (operando) | GPIO 18 | pino > resistor 220 Ω > LED > GND |
| LED amarelo (partindo/desligando) | GPIO 19 | idem |
| LED vermelho (parado/emergência) | GPIO 21 | idem |
| Relé opcional (liga com a máquina) | GPIO 23 | módulo relé; use `-1` para desativar |

Se não houver botões físicos, não precisa ligar nada: deixe `USAR_EMERGENCIA_FISICA false` para a emergência não disparar sozinha.

## Mensagens trocadas (texto, uma por linha)

- ESP32 → tablet: `START`, `STOP`, `EMERG`, `EMERG_OFF`
- Tablet → ESP32: `HELLO` ao conectar e `STATE:PARADO`, `STATE:PARTINDO`, `STATE:OPERANDO`, `STATE:PARANDO`, `STATE:EMERGENCIA` a cada mudança

Serviço BLE tipo UART (Nordic): `6e400001-b5a3-f393-e0a9-e50e24dcca9e`. Dá para testar com o app *nRF Connect*.
