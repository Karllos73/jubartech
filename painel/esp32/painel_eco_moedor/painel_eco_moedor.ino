/*
  Jubartech · Eco-Moedor Cerâmico
  Ponte Bluetooth (BLE) entre a ESP32 e o painel do tablet.

  O que faz:
   - Anuncia o nome "Jubartech-EcoMoedor" por Bluetooth Low Energy.
   - Botões físicos (opcionais) ligados à ESP32 comandam o painel:
       PARTIDA  -> envia "START"
       DESLIGAR -> envia "STOP"
       EMERGÊNCIA (com trava) -> envia "EMERG" ao apertar e "EMERG_OFF" ao liberar
   - Recebe do tablet o estado da máquina ("STATE:OPERANDO" etc.) e acende
     LEDs de sinaleiro no protótipo físico (verde, amarelo, vermelho) e um relé opcional.

  Placa: qualquer ESP32 com Bluetooth (ESP32 DevKit V1, por exemplo).
  Arduino IDE: instale "esp32 by Espressif Systems" no Gerenciador de Placas.
  Não precisa de biblioteca extra (usa a BLE que já vem com a placa).
  Funciona com o pacote esp32 versões 2.x e 3.x.

  Ligações (todas configuráveis abaixo):
   Botões: um terminal no pino, o outro no GND (usa o pull-up interno).
   LEDs:   pino -> resistor 220 Ω -> LED -> GND.
*/

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ---------------- Configuração ----------------
#define NOME_BLE        "Jubartech-EcoMoedor"

#define PINO_PARTIDA    25
#define PINO_DESLIGAR   26
#define PINO_EMERGENCIA 27
// Botão de emergência: false = contato NA (fecha ao apertar, mais comum em botões simples)
//                      true  = contato NF (abre ao apertar, padrão industrial)
// Se usar NF e não tiver botão ligado, deixe USAR_EMERGENCIA_FISICA = false.
#define EMERGENCIA_NF          false
#define USAR_EMERGENCIA_FISICA true

#define LED_VERDE       18   // operando
#define LED_AMARELO     19   // partindo / desligando (pisca)
#define LED_VERMELHO    21   // parado (fixo) / emergência (pisca)
#define PINO_RELE       23   // liga junto com "operando" (opcional; deixe -1 para não usar)

// UUIDs no padrão "UART" (Nordic). Os mesmos estão no painel do tablet.
#define UUID_SERVICO "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define UUID_RX      "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  // tablet -> ESP32
#define UUID_TX      "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  // ESP32 -> tablet
// ----------------------------------------------

BLEServer* servidor = nullptr;
BLECharacteristic* caracTX = nullptr;
volatile bool conectado = false;
bool estavaConectado = false;

String estado = "PARADO";        // último estado recebido do tablet
String filaRecebida = "";        // comando recebido aguardando processamento
portMUX_TYPE trava = portMUX_INITIALIZER_UNLOCKED;

// ---------- envio para o tablet ----------
void envia(const String& msg) {
  Serial.println("-> " + msg);
  if (!conectado || caracTX == nullptr) return;
  String linha = msg + "\n";
  caracTX->setValue((uint8_t*)linha.c_str(), linha.length());
  caracTX->notify();
}

// ---------- callbacks BLE ----------
class EventosServidor : public BLEServerCallbacks {
  void onConnect(BLEServer* s) override { conectado = true; }
  void onDisconnect(BLEServer* s) override { conectado = false; }
};

class EventosRX : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) override {
    String v = String(c->getValue().c_str());
    portENTER_CRITICAL(&trava);
    filaRecebida += v;
    portEXIT_CRITICAL(&trava);
  }
};

// ---------- botões com debounce ----------
struct Botao {
  int pino; bool ultimoLido; bool estavel; unsigned long mudouEm;
};
Botao bPartida  = {PINO_PARTIDA,    HIGH, HIGH, 0};
Botao bDesligar = {PINO_DESLIGAR,   HIGH, HIGH, 0};
Botao bEmerg    = {PINO_EMERGENCIA, HIGH, HIGH, 0};

// devolve true quando o estado estável muda
bool atualizaBotao(Botao& b) {
  bool lido = digitalRead(b.pino);
  if (lido != b.ultimoLido) { b.ultimoLido = lido; b.mudouEm = millis(); }
  if (millis() - b.mudouEm > 30 && lido != b.estavel) { b.estavel = lido; return true; }
  return false;
}

bool emergenciaApertada() {
  bool nivel = bEmerg.estavel;
  return EMERGENCIA_NF ? (nivel == HIGH) : (nivel == LOW);
}

// ---------- LEDs do sinaleiro ----------
void escreveLed(int pino, bool on) { if (pino >= 0) digitalWrite(pino, on ? HIGH : LOW); }

void atualizaLeds() {
  bool pisca = (millis() / 350) % 2;
  bool operando = estado == "OPERANDO";
  bool transicao = estado == "PARTINDO" || estado == "PARANDO";
  bool emergencia = estado == "EMERGENCIA";
  bool parado = estado == "PARADO";

  // sem tablet conectado: só o amarelo piscando devagar (aguardando)
  if (!conectado) {
    escreveLed(LED_VERDE, false);
    escreveLed(LED_AMARELO, (millis() / 1000) % 2);
    escreveLed(LED_VERMELHO, false);
    escreveLed(PINO_RELE, false);
    return;
  }
  escreveLed(LED_VERDE, operando);
  escreveLed(LED_AMARELO, transicao && pisca);
  escreveLed(LED_VERMELHO, parado || (emergencia && pisca));
  escreveLed(PINO_RELE, operando || estado == "PARTINDO");
}

void processaRecebidos() {
  String bloco;
  portENTER_CRITICAL(&trava);
  bloco = filaRecebida; filaRecebida = "";
  portEXIT_CRITICAL(&trava);
  if (bloco.length() == 0) return;

  int ini = 0;
  while (ini < (int)bloco.length()) {
    int fim = bloco.indexOf('\n', ini);
    if (fim < 0) fim = bloco.length();
    String linha = bloco.substring(ini, fim); linha.trim();
    ini = fim + 1;
    if (linha.length() == 0) continue;
    Serial.println("<- " + linha);
    if (linha.startsWith("STATE:")) estado = linha.substring(6);
    else if (linha == "HELLO") {
      // tablet acabou de conectar: informa se a emergência física está apertada
      if (USAR_EMERGENCIA_FISICA && emergenciaApertada()) envia("EMERG");
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_PARTIDA, INPUT_PULLUP);
  pinMode(PINO_DESLIGAR, INPUT_PULLUP);
  pinMode(PINO_EMERGENCIA, INPUT_PULLUP);
  int saidas[] = {LED_VERDE, LED_AMARELO, LED_VERMELHO, PINO_RELE};
  for (int p : saidas) if (p >= 0) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }

  // lê o estado inicial dos botões
  bPartida.ultimoLido = bPartida.estavel = digitalRead(PINO_PARTIDA);
  bDesligar.ultimoLido = bDesligar.estavel = digitalRead(PINO_DESLIGAR);
  bEmerg.ultimoLido = bEmerg.estavel = digitalRead(PINO_EMERGENCIA);

  BLEDevice::init(NOME_BLE);
  servidor = BLEDevice::createServer();
  servidor->setCallbacks(new EventosServidor());
  BLEService* servico = servidor->createService(UUID_SERVICO);

  caracTX = servico->createCharacteristic(UUID_TX, BLECharacteristic::PROPERTY_NOTIFY);
  caracTX->addDescriptor(new BLE2902());

  BLECharacteristic* caracRX = servico->createCharacteristic(
      UUID_RX, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  caracRX->setCallbacks(new EventosRX());

  servico->start();
  BLEAdvertising* anuncio = BLEDevice::getAdvertising();
  anuncio->addServiceUUID(UUID_SERVICO);
  anuncio->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("Pronto. Procure \"" NOME_BLE "\" no painel do tablet.");
}

void loop() {
  // reconexão: volta a anunciar quando o tablet desconecta
  if (!conectado && estavaConectado) { delay(300); BLEDevice::startAdvertising(); Serial.println("Tablet desconectou, anunciando de novo"); }
  if (conectado && !estavaConectado) Serial.println("Tablet conectado");
  estavaConectado = conectado;

  processaRecebidos();

  if (atualizaBotao(bPartida) && bPartida.estavel == LOW) envia("START");
  if (atualizaBotao(bDesligar) && bDesligar.estavel == LOW) envia("STOP");
  if (USAR_EMERGENCIA_FISICA && atualizaBotao(bEmerg)) envia(emergenciaApertada() ? "EMERG" : "EMERG_OFF");

  // comandos pelo Monitor Serial (115200) para testar sem botões: digite START, STOP, EMERG ou EMERG_OFF
  if (Serial.available()) { String c = Serial.readStringUntil('\n'); c.trim(); c.toUpperCase(); if (c.length()) envia(c); }

  atualizaLeds();
  delay(5);
}
