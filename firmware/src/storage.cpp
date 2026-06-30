/*
 * storage.cpp — Wrapper de persistência em NVS
 *
 * Fornece duas funções para carregar e salvar a struct Config usando a
 * biblioteca Preferences do ESP32, que abstrai a partição de
 * armazenamento não-volátil (NVS) na memória flash.
 *
 * Namespace NVS: NVS_NAMESPACE ("mold_cfg")
 * Chaves:
 *   NVS_KEY_TEMP_THRESH ("temp_thr") → float
 *   NVS_KEY_HUM_THRESH  ("hum_thr")  → float
 *
 * storageLoadConfig: lê o NVS e preenche a struct Config.
 *   Se uma chave estiver ausente (ex: primeiro boot), o valor padrão fornecido é mantido.
 *
 * storageSaveConfig: escreve ambos os limiares no NVS atomicamente.
 *   Chamada por vTaskComms sempre que o desktop envia novos limiares.
 *
 * Nenhuma primitiva FreeRTOS é usada aqui porque essas funções são sempre
 * chamadas de dentro de uma seção já protegida por xConfigMutex em vTaskComms.
 */

#include <Preferences.h>
#include <Arduino.h>
#include "config.h"
#include "types.h"

static Preferences prefs;

void storageLoadConfig(Config *cfg) {
    prefs.begin(NVS_NAMESPACE, /*somenteConsulta=*/true);

    // getFloat retorna o valor padrão (segundo argumento) se a chave não existir.
    cfg->temp_thresh = prefs.getFloat(NVS_KEY_TEMP_THRESH, cfg->temp_thresh);
    cfg->hum_thresh  = prefs.getFloat(NVS_KEY_HUM_THRESH,  cfg->hum_thresh);

    prefs.end();

    Serial.printf("[storage] Configuracao carregada — temp_thresh=%.1f  hum_thresh=%.1f\n",
                  cfg->temp_thresh, cfg->hum_thresh);
}

void storageSaveConfig(const Config *cfg) {
    prefs.begin(NVS_NAMESPACE, /*somenteConsulta=*/false);

    prefs.putFloat(NVS_KEY_TEMP_THRESH, cfg->temp_thresh);
    prefs.putFloat(NVS_KEY_HUM_THRESH,  cfg->hum_thresh);

    prefs.end();

    Serial.printf("[storage] Configuracao salva — temp_thresh=%.1f  hum_thresh=%.1f\n",
                  cfg->temp_thresh, cfg->hum_thresh);
}
