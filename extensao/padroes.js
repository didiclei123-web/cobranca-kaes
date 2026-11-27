/* Configurações iniciais (podem ser mudadas na aba Configurações). */
(function (raiz) {
  const CONFIG_PADRAO = {
    "clickup_url_lista": "",
    "status_alvo": [
      "Renovação Encaminhada",
      "Para Renovar",
      "Mensalistas - Ativos"
    ],
    "asaas_base": "https://www.asaas.com",
    "modelo_mensagem": "Olá, [NOME DO CLIENTE]!\n\nPassando para lembrar que sua fatura referente ao serviço de tráfego pago da KAES venceu no dia [DATA DE VENCIMENTO] e ainda está pendente:\n\n📌 Fatura de [DATA DE VENCIMENTO]\n🔗 Pague aqui: [LINK DE COBRANÇA]\n\nPedimos que regularize o pagamento o quanto antes para evitar a interrupção do serviço. Caso já tenha pago, é só nos enviar o comprovante.\n\nQualquer dúvida, fico à disposição!\n\nAtenciosamente,\nEquipe KAES",
    "modelo_mensagem_sem_juros": "Olá, [NOME DO CLIENTE]!\n\nPassando para lembrar que sua fatura referente ao serviço de tráfego pago da KAES venceu no dia [DATA DE VENCIMENTO] e ainda está pendente. Para facilitar, alteramos o vencimento para [NOVA DATA], sem cobrança de juros:\n\n📌 Fatura de [DATA DE VENCIMENTO] (novo vencimento: [NOVA DATA], sem juros)\n🔗 Pague aqui: [LINK DE COBRANÇA]\n\nPedimos que regularize o pagamento o quanto antes para evitar a interrupção do serviço. Caso já tenha pago, é só nos enviar o comprovante.\n\nQualquer dúvida, fico à disposição!\n\nAtenciosamente,\nEquipe KAES"
  };
  if (typeof module !== "undefined" && module.exports) module.exports = CONFIG_PADRAO;
  raiz.CONFIG_PADRAO = CONFIG_PADRAO;
})(typeof self !== "undefined" ? self : globalThis);
