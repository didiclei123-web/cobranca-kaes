# Cobranças KAES

Programa para Windows que confere os clientes vencidos no ClickUp, busca as cobranças no Asaas,
gera as mensagens de cobrança e atualiza o ClickUp — tudo por cliques no navegador (sem API).

**Para usar:** baixe o `CobrancasKAES-Windows.zip` mais recente em **Releases**, descompacte e abra
`CobrancasKAES.exe`. Não precisa instalar nada. Instruções em `LEIA-ME.txt`.

Este repositório não guarda logins nem dados de clientes: tudo isso fica só na pasta `dados`
do computador onde o programa roda.

## Código
- `app/gui.py` — janela
- `app/motor.py` — passo a passo (conferir, mensagens, atualizar)
- `app/navegador.py` — cliques no ClickUp e no Asaas (Edge, via Playwright)
- `app/regras.py` — datas, nomes, correspondência e comandos
- `app/ia_local.py` — IA local opcional (Ollama)
- `.github/workflows/build.yml` — monta o `.exe` a cada atualização
