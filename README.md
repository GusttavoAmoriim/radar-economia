# Radar Economia

Coleta séries econômicas de APIs oficiais (BCB/SGS e IBGE/SIDRA) para SQLite, gera um painel com gráficos e avisa no Telegram.

    pip install -r requirements.txt
    python coletor.py coletar          # busca tudo e verifica alertas (Windows: iniciar.bat)
    python coletor.py painel           # gera e abre dados/painel.html
    python coletor.py ultimos ipca_mensal 12
    python coletor.py agendar 6        # coleta + alertas a cada 6 horas (deixe a janela aberta)
    python coletor.py sidra "/t/5932/n1/all/v/all/p/last%203/c11255/90707"   # conferir uma consulta SIDRA

Séries em `series.yaml`; regras de alerta em `alertas.yaml`. Dados em `dados/economia.db`.

## Telegram
1. No Telegram, fale com **@BotFather**, envie `/newbot` e guarde o token.
2. Mande qualquer mensagem para o seu bot novo, depois abra `https://api.telegram.org/bot<TOKEN>/getUpdates` e copie o número em `"chat":{"id":...}`.
3. Copie `.env.example` para `.env` e preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Não compartilhe o `.env`.
4. Mais fácil: mande "oi" ao seu bot e rode `python coletor.py telegram-chat-id`: ele mostra o chat id.
5. `python coletor.py testar-telegram` deve mandar uma mensagem de teste.

Na primeira execução os alertas só registram o estado atual (não avisam). Depois, cada alerta avisa uma vez por mudança. Sem Telegram configurado, os avisos aparecem na tela e ficam pendentes.

Testes: `pip install pytest && pytest`.
