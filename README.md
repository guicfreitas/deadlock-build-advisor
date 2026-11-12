<div align="center">

# Deadlock Build Advisor

**Builds de counter para Deadlock, montadas na hora a partir dos heróis da sua partida.**

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Plataforma](https://img.shields.io/badge/plataforma-Windows-0078D6?logo=windows&logoColor=white)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-nenhuma-brightgreen)
![VAC](https://img.shields.io/badge/VAC-seguro-success)

</div>

Quando a partida começa, o app descobre quem são os seus adversários e monta três recomendações:

| | O que é | Contra quem |
|---|---|---|
| 🛡️ **Build de lane** | itens dos primeiros ~10 minutos, dentro de um orçamento realista de almas | a dupla da **sua lane** |
| ⚔️ **Build geral** | itens de mid e late game | o **time inimigo inteiro** |
| 🎯 **Counters por adversário** | os itens com maior vantagem contra cada inimigo (ex.: *Metal Skin* contra Haze) e a sua win rate no confronto | cada inimigo |

As recomendações aparecem num **overlay sempre visível** por cima do jogo e numa **página web local** (`http://localhost:8787`), que você pode abrir no navegador do overlay da Steam (Shift+Tab), num segundo monitor ou no celular.

> [!NOTE]
> Funciona nos modos **casual** e **competitivo** (mapa padrão 6v6). A **Street Brawl** (4v4) não é suportada, porque lá os itens vêm por draft e não são comprados. O app detecta esse modo e apenas avisa.

## É seguro? (VAC)

**Sim.** O app **não injeta nada no jogo, não lê a memória do processo e não modifica arquivos do jogo**. Ele só:

- lê o `console.log`, um arquivo de texto que o próprio jogo grava quando é iniciado com `-condebug`;
- consulta a API pública da comunidade [deadlock-api.com](https://deadlock-api.com);
- desenha uma janela própria do Windows por cima do jogo.

Por que não ler os heróis direto do jogo? Porque o Deadlock não expõe essa informação de forma segura: não existe Game State Integration, o combat log fica desligado no matchmaking e o comando `status` só mostra nomes. O broadcast ao vivo da Valve, acessado pela deadlock-api, é a única fonte que não encosta no jogo.

## Início rápido

**Requisitos:** Windows, [Python 3.10+](https://www.python.org/downloads/) (marque "Add Python to PATH" na instalação) e o Deadlock na Steam. Não há nenhuma dependência para instalar.

1. **Ative o log do jogo.** Na Steam: Deadlock → Propriedades → Opções de inicialização → adicione `-condebug`.
2. **Use janela sem bordas.** No jogo, coloque o modo de tela em *Janela sem bordas* (Borderless). Em tela cheia, o overlay não aparece por cima.
3. **Baixe o app.** `git clone` este repositório ou baixe o ZIP (botão *Code* → *Download ZIP*).
4. **Pronto, não precisa configurar nada.** O app acha a pasta do jogo e a sua conta pelas bibliotecas da Steam, e avisa se faltar o `-condebug`.
5. **Rode** `run.bat` (ou, no PowerShell: `$env:PYTHONPATH="src"; python -m deadlock_advisor`).
6. **Entre numa partida.** O status muda para "Partida encontrada" e a build aparece logo em seguida.

> [!TIP]
> Se a detecção falhar (ex.: Steam instalada num lugar incomum), defina `game_dir` no `config.json`. Para achar a pasta, na Steam: Deadlock → Propriedades → Arquivos instalados → **Procurar**.

## Uso

- **Automático**: deixe o app aberto. Numa partida casual de teste, a build ficou pronta cerca de 85 s depois de a partida ser encontrada, praticamente quando o relógio do jogo chegou a 0:00. O atraso é do broadcast da Valve, não do app.
- **Troca de lane**: nos primeiros 5 minutos, o app continua acompanhando a partida. Se a dupla inimiga da sua lane mudar, ele refaz a build de lane e avisa no status.
- **Overlay**: arraste com o botão esquerdo, dê duplo-clique para recolher e clique com o botão direito para fechar.
- **Modo manual** (na página web): escolha o seu herói e marque os inimigos. Um clique marca como inimigo; um segundo clique marca como inimigo de lane.
- **Linha de comando**:

```powershell
$env:PYTHONPATH="src"
python -m deadlock_advisor --hero Infernus --enemies "Abrams,Haze,Seven,Lady Geist,Ivy,Mina" --lane "Abrams,Haze"
python -m deadlock_advisor --match-id 135235741   # força uma partida específica
```

## Configuração

Todas as opções são opcionais. Copie `config.example.json` para `config.json` e mude só o que precisar.

| Campo | Padrão | Para quê |
|---|---|---|
| `game_dir` | detectado pela Steam | pasta de instalação do jogo |
| `account_id` | detectado pela Steam | seu SteamID3, caso a detecção automática falhe |
| `api_key` | — | chave opcional da deadlock-api. Sem ela, o limite é de ~6 partidas espectadas por hora. Também pode vir da variável `DEADLOCK_API_KEY`. |
| `port` | `8787` | porta da página web local |
| `overlay` | `true` | liga ou desliga o overlay |
| `overlay_alpha` | `0.88` | transparência do overlay |
| `engine.lane_window_s` | `600` | duração da fase de lane, em segundos |
| `engine.lane_budget` | `5600` | almas gastas na lane |
| `engine.filters` | `{}` | filtros da API, ex.: `{"min_average_badge": 80}` para considerar só partidas de rank alto |

O `config.json` fica fora do Git, então a sua chave e o seu ID não vão parar no repositório.

## Como funciona

```
console.log  ──(match_id=...)──►  watcher  ──►  deadlock-api live broadcast (SQL)
                                                  │  heróis, times e lanes dos 12 jogadores
                                                  ▼
                       deadlock-api analytics  ──►  motor de recomendação  ──►  overlay + web UI
                       (item-stats, hero-counter-stats)
```

1. Ao entrar numa partida, o jogo grava `... match_id=135235741` no `console.log`.
2. O app pede para a deadlock-api espectar a partida e lê do broadcast ao vivo o herói, o time e a lane de cada jogador. A sua conta é detectada pelo arquivo `citadel/account_<id>.stats`.
3. O motor compara, para o seu herói, a win rate de cada item **contra esses adversários** com a win rate **geral** do item. A diferença é o *lift*:
   - as win rates são suavizadas (prior bayesiano) para que itens com poucas partidas não dominem a lista;
   - o efeito do matchup em si (por exemplo, "Infernus perde 3% a mais contra Haze") é descontado, para que o lift meça o item e não o confronto;
   - a build de lane usa só compras feitas até `lane_window_s`, filtradas para jogadores que estavam na mesma lane do inimigo.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| "Falta -condebug nas opções de inicialização" ou "console.log não encontrado em …" | Falta o `-condebug` nas opções de inicialização, ou o `game_dir` está errado. Confira se existe `game\citadel\console.log` dentro da pasta do jogo. |
| O status nunca sai de "Aguardando partida…" | O jogo foi aberto sem `-condebug`. Feche o Deadlock, adicione a opção e abra de novo. |
| "account_id não detectado" ou "Sua conta não foi encontrada nesta partida" | Defina o seu SteamID3 em `account_id` no `config.json`. |
| Erro ao ler os jogadores depois de várias partidas seguidas | Sem chave, a deadlock-api deixa espectar ~6 partidas por hora. Espere ou configure uma `api_key`. Enquanto isso, use o modo manual. |
| O overlay não aparece por cima do jogo | O jogo está em tela cheia. Mude para *Janela sem bordas*. |
| A build demora a aparecer | Normal: o broadcast da Valve tem atraso de cerca de 1 minuto e meio. |
| `python` não é reconhecido | O Python não está no PATH. Reinstale marcando "Add Python to PATH". |

## Desenvolvimento

```powershell
pip install pytest
python -m pytest -q -p no:anyio
```

```
src/deadlock_advisor/
  logwatch.py   lê o console.log e detecta início e fim de partida
  live.py       descobre o roster (heróis, times, lanes) pelo broadcast ao vivo
  api.py        cliente da deadlock-api com cache em disco
  engine.py     motor de recomendação (lift, suavização, builds de lane e geral, counters)
  app.py        orquestração e estado compartilhado
  server.py     servidor web local e API JSON
  overlay.py    overlay tkinter sempre no topo
  web/          interface web
tests/
```

Contribuições são bem-vindas: abra uma *issue* com bugs ou ideias, ou mande um *pull request*. O projeto usa só a biblioteca padrão do Python; se uma mudança precisar de dependência, discuta antes numa issue.

## Roadmap

- [ ] Reavaliar a build durante a partida com os itens que os inimigos compraram (o broadcast ao vivo traz isso).
- [ ] Ajustar automaticamente o filtro de rank ao seu rank (`/v1/players/{id}/rank`).
- [ ] Recomendar a ordem de habilidades (`/v1/analytics/ability-order-stats`).
- [ ] Atalho global para mostrar ou esconder o overlay.
- [ ] Exportar a build para o formato de Hero Builds do jogo.

## Créditos

Os dados de partidas e estatísticas vêm da [deadlock-api.com](https://deadlock-api.com), um projeto da comunidade. Considere apoiá-los.

Este projeto não é afiliado à Valve Corporation. Deadlock e os nomes dos heróis e itens são marcas da Valve.
