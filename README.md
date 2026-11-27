# Cobranças KAES

Programa para Windows que confere os clientes vencidos no ClickUp, busca as cobranças no Asaas,
gera as mensagens de cobrança e atualiza o ClickUp — tudo por cliques no navegador (sem API).

**Para usar (recomendado):** baixe `CobrancasKAES-Extensao-Edge.zip` em **Releases**, descompacte numa pasta fixa
e siga o `COMO-INSTALAR.txt`. É uma extensão do Edge com painel lateral: funciona mesmo com o
Controle Inteligente de Aplicativos do Windows ligado.

Também existe a versão `.exe` (`CobrancasKAES-Windows.zip`), que é bloqueada quando o Controle Inteligente está ligado.

Este repositório não guarda logins nem dados de clientes: tudo isso fica só na pasta `dados`
do computador onde o programa roda.

## Código
- `extensao/` — extensão do Edge (painel, regras, motor, cliques)
- `testes-extensao/` — testes da lógica e teste completo num Chrome com sites que imitam ClickUp/Asaas
- `app/gui.py` — janela
- `app/motor.py` — passo a passo (conferir, mensagens, atualizar)
- `app/navegador.py` — cliques no ClickUp e no Asaas (Edge, via Playwright)
- `app/regras.py` — datas, nomes, correspondência e comandos
- `app/ia_local.py` — IA local opcional (Ollama)
- `.github/workflows/build.yml` — monta o `.exe` a cada atualização
