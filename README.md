# Deadlock Build Advisor

Quando uma partida de **Deadlock** começa, o app descobre quem são os seus adversários e monta:

1. **Build de lane**: os itens dos primeiros ~10 minutos que mais rendem contra a dupla que está na **sua lane**, dentro de um orçamento de almas realista.
2. **Build geral** (mid e late game): os itens que mais rendem para o seu herói contra o **time inimigo inteiro**.
3. **Counters por adversário**: para cada inimigo, os itens com maior vantagem contra ele (ex.: *Metal Skin* contra Haze) e a sua win rate no confronto.

As recomendações aparecem num **overlay sempre visível** por cima do jogo e numa **página web local** (`http://localhost:8787`), que você pode abrir no navegador do overlay da Steam (Shift+Tab), num segundo monitor ou no celular.

## É seguro? (VAC)

Sim. O app **não injeta nada no jogo, não lê memória e não modifica arquivos do jogo**. Ele só:
- lê o `console.log` que o próprio jogo grava em texto quando é iniciado com `-condebug`;
- consulta a API pública da comunidade [deadlock-api.com](https://deadlock-api.com);
- desenha uma janela própria do Windows por cima do jogo.

## Como funciona

```
console.log  ──(match_id=...)──►  watcher  ──►  deadlock-api live broadcast (SQL)
                                                  │  heróis, times e lanes dos 12 jogadores
                                                  ▼
                       deadlock-api analytics  ──►  motor de recomendação  ──►  overlay + web UI
                       (item-stats, hero-counter-stats)
```

1. Ao entrar numa partida, o jogo grava `... match_id=135235741` no `console.log`.
2. O app pede para a deadlock-api espectar a partida e lê do broadcast ao vivo o `hero_id`, o time e a lane de cada jogador. A sua conta é detectada automaticamente pelo arquivo `citadel/account_<id>.stats`.
3. O motor compara, para o seu herói, a win rate de cada item **contra esses adversários** com a win rate **geral** do item. A diferença é o *lift*:
   - as win rates são suavizadas (prior bayesiano) para que itens com poucas partidas não dominem;
   - o efeito do matchup em si (por exemplo, "Infernus perde 3% a mais contra Haze") é removido, para o lift medir o item e não o confronto;
   - a build de lane usa só compras feitas até `lane_window_s` (600 s), filtradas para jogadores na mesma lane do inimigo (`same_lane_filter`).

## Instalação

Requer **Python 3.10+**, sem dependências externas.

1. Na Steam: Deadlock → Propriedades → Opções de inicialização → adicione `-condebug`.
2. Jogue em **Janela sem bordas** (Borderless), senão o overlay não aparece por cima do jogo.
3. Rode `run.bat`, ou:

```powershell
$env:PYTHONPATH="src"; python -m deadlock_advisor
```

Se quiser personalizar, copie `config.example.json` para `config.json`.

| Campo | Padrão | Para quê |
|---|---|---|
| `game_dir` | `D:\SteamLibrary\steamapps\common\Deadlock` | pasta do jogo |
| `account_id` | auto | seu SteamID3, se a detecção automática falhar |
| `api_key` | — | chave opcional da deadlock-api (sem ela, o limite é de ~6 partidas espectadas por hora) |
| `overlay` | `true` | liga ou desliga o overlay |
| `engine.lane_window_s` | `600` | duração da fase de lane, em segundos |
| `engine.lane_budget` | `5600` | almas gastas na lane |
| `engine.filters` | `{}` | filtros da API, ex.: `{"min_average_badge": 80}` para considerar só partidas de rank alto |

## Uso

- **Automático**: deixe o app aberto. Ao entrar na partida, o status muda para "Partida encontrada" e a build aparece em cerca de 1 a 2 minutos (o broadcast da Valve tem um atraso).
- **Overlay**: arraste com o botão esquerdo, dê duplo-clique para recolher e clique com o botão direito para fechar.
- **Modo manual** (na página): escolha o seu herói e marque os inimigos. Um clique marca como inimigo e um segundo clique marca como inimigo de lane.
- **Linha de comando**:

```powershell
$env:PYTHONPATH="src"
python -m deadlock_advisor --hero Infernus --enemies "Abrams,Haze,Seven,Lady Geist,Ivy,Mina" --lane "Abrams,Haze"
python -m deadlock_advisor --match-id 135235741   # forçar uma partida
```

## Testes

```powershell
pip install pytest
python -m pytest -q -p no:anyio
```

## Estrutura

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

## Roadmap

- [ ] Reavaliar a build durante a partida com os itens que os inimigos compraram (o broadcast ao vivo traz isso).
- [ ] Ajustar automaticamente o filtro de rank ao seu rank (`/v1/players/{id}/rank`).
- [ ] Recomendar a ordem de habilidades (`/v1/analytics/ability-order-stats`).
- [ ] Atalho global para mostrar ou esconder o overlay.
- [ ] Exportar a build para o formato de Hero Builds do jogo.
