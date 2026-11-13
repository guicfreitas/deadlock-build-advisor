<div align="center">

**[English](README.md) · Português (Brasil)**

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

E durante a partida:

- 📋 **Copiar para o jogo**: um clique copia a build no formato de guia do Deadlock. No jogo, é só abrir *Explorar guias*, criar um guia e clicar em **Colar guia**: as categorias, os itens e as anotações entram prontos, e a Compra rápida passa a seguir a build.
- 🔄 **Troque para counterar**: a cada minuto o app lê o que os inimigos compraram e, se aparecer uma ameaça (muita cura, dano de arma, dano espiritual, controle, resistências), sugere no topo da tela "compre X em vez de Y" na build que você colou, dizendo quem comprou o quê.

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

1. **Baixe e rode o instalador** `DeadlockBuildAdvisor-Setup-x.y.z.exe` (na página de *Releases*). Não precisa de Python nem de nada além dele, e não pede senha de administrador.
2. **Ative o log do jogo.** Na Steam: Deadlock → Propriedades → Opções de inicialização → adicione `-condebug`.
3. **Use janela sem bordas.** No jogo, coloque o modo de tela em *Janela sem bordas* (Borderless). Em tela cheia, o overlay não aparece por cima.
4. **Abra o app** pelo atalho *Deadlock Build Advisor*. Ele acha sozinho a pasta do jogo e a sua conta pelas bibliotecas da Steam. Na primeira vez, a página mostra um passo a passo (achar o Deadlock → ativar o `-condebug` → abrir o jogo) que se marca sozinho conforme você avança.
5. **Entre numa partida.** O status muda para "Partida encontrada" e a build aparece logo em seguida.

O app abre uma janelinha de controle (abrir a página, mostrar ou esconder o overlay, configurações, sair). Fechar essa janela fecha o app. Se você abrir o atalho de novo com o app já aberto, ele só mostra a página.

> [!TIP]
> Se a detecção falhar (ex.: Steam instalada num lugar incomum), defina a pasta do jogo em **Configurações**, na página do app. Para achar a pasta, na Steam: Deadlock → Propriedades → Arquivos instalados → **Procurar**.

<details>
<summary>Rodar a partir do código-fonte</summary>

Requer [Python 3.10+](https://www.python.org/downloads/), sem dependências externas. `git clone` este repositório e rode `run.bat`, ou:

```powershell
$env:PYTHONPATH="src"; python -m deadlock_advisor
```

</details>

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

## Idiomas

O app fala **English, Português (Brasil), Español, Русский e 简体中文** e segue o idioma do Windows (dá para trocar em Configurações; vale depois de reiniciar). Nomes de heróis e itens vêm no mesmo idioma. Para adicionar outro idioma, copie `src/deadlock_advisor/locales/en.json`, traduza os valores e registre o código em `LANGUAGES` no `i18n.py`.

## Configuração

Todas as opções são opcionais e ficam na seção **Configurações** da página do app, com explicação de cada campo. Elas são salvas em `%APPDATA%\deadlock-advisor\config.json` (rodando a partir do código-fonte, um `config.json` na pasta do projeto tem prioridade). Só o que você mudar é gravado: o resto continua automático.

| Campo | Padrão | Para quê |
|---|---|---|
| `game_dir` | detectado pela Steam | pasta de instalação do jogo |
| `account_id` | detectado pela Steam | seu SteamID3, caso a detecção automática falhe |
| `api_key` | — | chave opcional da deadlock-api. Sem ela, o limite é de ~6 partidas espectadas por hora. Também pode vir da variável `DEADLOCK_API_KEY`. |
| `port` | `8787` | porta da página web local |
| `overlay` | `true` | liga ou desliga o overlay |
| `overlay_alpha` | `0.88` | transparência do overlay |
| `auto_update` | `true` | baixa e instala versões novas sozinho, fora de partida |
| `update_repo` | `guicfreitas/deadlock-build-advisor` | repositório do GitHub cujas *releases* o app segue |
| `engine.lane_window_s` | `600` | duração da fase de lane, em segundos |
| `engine.lane_budget` | `5600` | almas gastas na lane |
| `engine.filters` | `{}` | filtros da API, ex.: `{"min_average_badge": 80}` para considerar só partidas de rank alto |

A pasta do jogo e a porta só mudam depois de reiniciar o app; a página oferece um botão para isso. O resto vale na hora. O log fica em `%LOCALAPPDATA%\deadlock-advisor\advisor.log`.

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
4. A **ordem das habilidades** vem da árvore de ordens de upgrade dos jogadores do herói (`/v1/analytics/ability-order-tree`, últimos 14 dias). O app percorre a árvore ponto a ponto: segue a escolha mais comum e só troca por outra quando ela é usada por pelo menos 25% dos jogadores daquele passo e ganha mais. A win rate só é comparada entre escolhas do mesmo passo, porque ordens mais longas ganham mais só por pertencerem a partidas vencidas (quem ganha sobe de nível mais rápido). A ordem vai junto no guia colado no jogo.

### Atualizações

O app instalado confere as *releases* do GitHub ao abrir e a cada 6 horas. Quando sai uma versão nova, ele baixa o instalador, confere o SHA-256 e instala sozinho assim que você não estiver em partida; o app fecha e reabre em poucos segundos. Também dá para instalar na hora pelo botão **Atualizar agora**, ou desligar isso em Configurações.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| "O log do jogo não está ativado" ou "O log do jogo ainda não existe" | Falta o `-condebug` nas opções de inicialização, ou a pasta do jogo está errada. Confira se existe `game\citadel\console.log` dentro da pasta do jogo. |
| O status nunca sai de "Aguardando partida…" | O jogo foi aberto sem `-condebug`. Feche o Deadlock, adicione a opção e abra de novo. |
| "Não encontrei sua conta Steam" ou "Sua conta não foi encontrada nesta partida" | Informe o número da sua conta Steam em **Configurações**. |
| Erro ao ler os jogadores depois de várias partidas seguidas | Sem chave, a deadlock-api deixa espectar ~6 partidas por hora. Espere ou configure uma `api_key`. Enquanto isso, use o modo manual. |
| O overlay não aparece por cima do jogo | O jogo está em tela cheia. Mude para *Janela sem bordas*. |
| A build demora a aparecer | Normal: o broadcast da Valve tem atraso de cerca de 1 minuto e meio. |
| `python` não é reconhecido | O Python não está no PATH. Reinstale marcando "Add Python to PATH". |

## Desenvolvimento

```powershell
pip install pytest
python -m pytest -q -p no:anyio
```

Gerar o `.exe` e o instalador (só para quem distribui; o app em si não tem dependências):

```powershell
python -m venv .venv-build; .venv-build\Scripts\pip install pyinstaller
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # -> dist\DeadlockBuildAdvisor-Setup-x.y.z.exe (+ .sha256)
```

Publicar uma versão (é o que os apps instalados baixam):

1. Suba `__version__` em `src/deadlock_advisor/__init__.py` (e em `pyproject.toml`) e rode o `build.ps1`.
2. No GitHub, crie uma *release* com a tag `vX.Y.Z` e anexe `DeadlockBuildAdvisor-Setup-X.Y.Z.exe` e o `.sha256`.
   O repositório precisa ser público: o app consulta a API do GitHub sem login.

```
src/deadlock_advisor/
  logwatch.py   lê o console.log e detecta início e fim de partida
  live.py       descobre o roster (heróis, times, lanes) pelo broadcast ao vivo
  api.py        cliente da deadlock-api com cache em disco
  engine.py     motor de recomendação (lift, suavização, builds de lane e geral, counters)
  app.py        orquestração e estado compartilhado
  server.py     servidor web local e API JSON
  overlay.py    overlay tkinter sempre no topo
  panel.py      janela de controle do app instalado
  steam.py      acha o jogo, a conta e as opções de inicialização pela Steam
  gamebuild.py  exporta a build como guia para o "Colar guia" do jogo
  abilities.py  escolhe a ordem das habilidades pela árvore de ordens dos jogadores
  updater.py    confere, baixa e instala versões novas (GitHub Releases)
  counters.py   sugere trocas a partir dos itens que os inimigos compraram
  i18n.py       idiomas (locales/*.json servem o Python e a página)
  about.py      links de feedback e apoio
  web/          interface web
packaging/      ícone, PyInstaller e instalador (Inno Setup)
tests/
```

Encontrou um bug ou tem uma ideia? Use **Feedback e ajuda** na página do app (ele já abre uma *issue* com a versão preenchida) ou abra uma *issue* aqui. O código é publicado só para consulta (veja a [Licença](#licença)), então *pull requests* e forks modificados não são aceitos.

## Roadmap

- [ ] Ajustar automaticamente o filtro de rank ao seu rank (`/v1/players/{id}/rank`).
- [x] Recomendar a ordem de habilidades e incluí-la no guia colado.
- [x] Atualização automática.
- [ ] Atalho global para mostrar ou esconder o overlay.

## Licença

Todos os direitos reservados. O código está aqui só para consulta: você pode ver o código e usar o app pelos instaladores oficiais, para uso pessoal e não comercial. Copiar, modificar, redistribuir ou vender, no todo ou em parte, não é permitido sem autorização por escrito. Veja o arquivo [LICENSE](LICENSE).

## Créditos

Os dados de partidas e estatísticas vêm da [deadlock-api.com](https://deadlock-api.com), um projeto da comunidade. Considere apoiá-los.

Este projeto não é afiliado à Valve Corporation. Deadlock e os nomes dos heróis e itens são marcas da Valve.
