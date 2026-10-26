# Publicar no GitHub (coleta e painel automáticos)

Resultado: a cada 6 horas o GitHub coleta as séries, manda os alertas no Telegram e atualiza o painel num link que você abre no celular.

## 1. Criar o repositório
1. Em github.com, **New repository**. Nome: `radar-economia`. Marque **Public**. Não marque README nem .gitignore.
2. Copie o endereço que aparece (`https://github.com/SEU-USUARIO/radar-economia.git`).

## 2. Enviar o projeto
Precisa do Git (`winget install --id Git.Git -e`; depois abra um terminal novo). Na pasta `D:\radar-economia`:

    git init
    git add .
    git status

**Confira que `.env` NÃO aparece na lista** (ele tem o seu token). Aparecendo `dados/economia.db` e `.github/workflows/coletar.yml`, siga:

    git commit -m "Radar Economia"
    git branch -M main
    git remote add origin https://github.com/SEU-USUARIO/radar-economia.git
    git push -u origin main

## 3. Guardar o Telegram como segredo
No repositório: **Settings → Secrets and variables → Actions → New repository secret**. Crie dois:
- `TELEGRAM_BOT_TOKEN` (o token novo)
- `TELEGRAM_CHAT_ID`

## 4. Ligar o painel
**Settings → Pages → Build and deployment → Source: GitHub Actions**.

## 5. Primeira execução
Aba **Actions → Coletar e publicar → Run workflow**. Quando ficar verde, o endereço do painel aparece no fim da execução (algo como `https://SEU-USUARIO.github.io/radar-economia/`). Salve na tela inicial do celular.

Se der erro de permissão ao gravar o banco: **Settings → Actions → General → Workflow permissions → Read and write**.

## Depois disso
- **Pare de rodar o `agendar` no computador.** Dois bancos (o seu e o do GitHub) saem de sincronia. Se quiser coletar localmente de novo, rode `git pull` antes.
- Séries e alertas: edite `series.yaml` e `alertas.yaml` e envie com `git add . && git commit -m "ajuste" && git push`.
- Mudar a frequência: altere o `cron` em `.github/workflows/coletar.yml`.
- Se o BCB recusar pedidos vindos do GitHub (as séries do BCB falham em toda execução), me avise: a alternativa é rodar num servidor próprio.
