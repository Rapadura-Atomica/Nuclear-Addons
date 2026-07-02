# Generate Auto Matte

Addon de Grease Pencil para Blender (4.3+ / 5.0) focado em quem trabalha com **board / storyboard**. Reúne duas ferramentas:

- **Generate Auto Matte** — com um clique, preenche **todas as regiões fechadas** do seu line art com uma cor chapada (cinza por padrão) numa camada dedicada chamada **`AutoMatte`**, posicionada atrás do desenho.
- **Cleanup Lines** — seleciona um amontoado de traços de **rascunho sujos/sobrepostos** e transforma em **uma única linha limpa e suave**.

## Como usar

1. Selecione um objeto de Grease Pencil e entre em modo **Draw** ou **Edit**.
2. Abra a sidebar (`N`) → aba **Auto Matte**.
3. Clique em **Generate Auto Matte**. No diálogo:
   - **Matte Color** — cor de preenchimento (cinza por padrão).
   - **Line Art Layer** — camada que define as regiões. Vazio = camada ativa.
   - **Frames** — `Current Frame` (só o frame ativo) ou `All Keyframes` (gera a matte
     para **todos os keyframes** da camada de line art de uma vez — segue a animação
     inteira num clique; ex.: uma bola pulando vira matte em cada pose).
   - **Precision** — junta pontos próximos. Valores menores fecham buracos/frestas maiores no traço.
   - **Keep Holes** — recorta o espaço negativo interno (ex.: anéis) como buracos reais via material *holdout*.
   - **Clear Previous Matte** — limpa a matte anterior antes de gerar (em `All Keyframes`,
     apaga todos os keyframes de matte antes para um re-bake limpo).

### Animação (All Keyframes)

Cada keyframe da camada de line art vira um keyframe correspondente na camada `AutoMatte`,
no mesmo número de frame. Como os dados de cada keyframe do Grease Pencil são lidos
diretamente, o bake não precisa percorrer/alterar o frame atual da cena — roda tudo de uma vez.
Reaplicar com **Clear Previous Matte** ligado refaz a matte de toda a animação do zero.

O resultado vai para a camada `AutoMatte` (criada automaticamente, atrás do line art), usando os materiais `AutoMatte` e `AutoMatte Holdout`.

## Cleanup Lines (Ink) — recomendado

Cleanup por **tinta** (esqueleto), o modo mais robusto para transformar um rascunho sujo em
line art limpo. Em vez de agrupar traços, ele rasteriza toda a tinta selecionada, afina até a
**linha central** e a decompõe em linhas limpas — **unificando** rabiscos sobrepostos numa
linha só e **absorvendo os ticks** que cruzam. Quase sem parâmetro:

1. Em **Edit**, selecione o desenho (pode ser tudo de uma vez).
2. Sidebar → **Auto Matte** → **Cleanup Lines (Ink)**.
   - **Ink Merge** — quão grossa a tinta é engrossada antes de achar o centro. Maior funde
     rabiscos mais soltos, mas pode grudar linhas próximas.
   - **Min Detail** — descarta galhos curtos (ticks/specks). Maior remove mais detalhe pequeno.
   - **Thickness / Scale**, **Inherit Color**, **Keep Original** como nos outros modos.

Usa `scipy` + `scikit-image` (ver `dependencias_INSTALL.md`); sem elas, cai num afinamento
Zhang-Suen em numpy puro (funciona, qualidade menor). Os modos abaixo são **legados**
(baseados em traço) e não precisam de dependências.

## Cleanup Lines (legado, baseado em traço)

Pega vários traços de rascunho que descrevem **uma mesma linha** e os funde numa única
linha concreta e suave — ideal para fechar um esboço sujo virando line art limpo.

1. Em modo **Edit**, selecione os traços de rascunho que formam a linha.
2. Sidebar (`N`) → aba **Auto Matte** → **Cleanup Lines**. No diálogo:
   - **Merge Distance** — traços mais próximos que isso são fundidos. Aumente para juntar um
     amontoado mais solto/bagunçado.
   - **Closed Shape** — trata a seleção como um laço fechado em vez de linha aberta.
   - **Ignore Transparent** — ignora pontos com opacidade zero.
   - **Trim Loose Ends / Trim Amount** — corta as "pontas soltas e tortas" (overshoots/
     ganchos) nas extremidades, onde o rascunho afina para um único traço perdido. Ligado
     por padrão; **Trim Amount** controla o quanto recua (0 = não apara). Só apara as
     **pontas** — o miolo e linhas finas uniformes são preservados.
   - **Smooth** / **Roundness** — suavização (média de vértices) e arredondamento (corte de
     cantos Chaikin). Padrões **baixos** (1/1) de propósito: a ideia é *unir* os traços
     preservando o formato do desenho, não redesenhar como uma curva genérica. Aumente só
     se a linha ficar trêmula.
   - **Resample / Spacing** — **desligado** por padrão (mantém a densidade de pontos
     original = mais detalhe). Ligue para simplificar em pontos igualmente espaçados.
   - **Uniform Thickness / Thickness / Thickness Scale** — espessura da linha. Com *Uniform
     Thickness* ligado (padrão) a linha tem espessura única; **Thickness** define o raio
     (0 = usa a espessura média do rascunho) e **Thickness Scale** multiplica o resultado.
     Desligue *Uniform Thickness* para herdar a pressão variável do traço original.
   - **Inherit Color** — herda a cor de vértice média dos traços originais.
   - **Keep Original Strokes** — por padrão **substitui** o rascunho pela linha limpa
     (apaga exatamente os traços selecionados, identificados por hash estável); ligue
     para manter os traços originais.

A linha resultante herda os atributos médios (pressão/espessura, opacidade, cor, UV) do
rascunho. Funciona na camada e frame ativos.

> **Cleanup Lines** funde **tudo que está selecionado em UMA linha**. Para um desenho com
> várias linhas (ex.: um coqueiro com folhas, tronco e grama), use o **Multi** abaixo, ou
> limpe um elemento de cada vez.

### Cleanup Lines (Multi) — vários traços de uma vez

Seleciona tudo, **agrupa** os traços por proximidade/direção e limpa **cada grupo na sua
própria linha**. Ideal para fechar um desenho inteiro de uma vez.

- **Group By** — como dividir a seleção em linhas:
  - *Overlap* (**padrão**) — funde traços que **correm lado a lado por boa parte do
    comprimento** (duplicatas da mesma linha). **Min Overlap** (%) = quanto de um traço
    precisa acompanhar o outro; **Overlap Distance** = o quão perto contam como "lado a
    lado". É o modo ideal para inking sobre rascunho: evita o efeito de "tudo vira uma
    linha só" que os critérios por distância sofrem num desenho conectado (ex.: folhas que
    se encontram no centro do coqueiro).
  - *Distance (Relative)* — separa onde o vão é grande relativo ao comprimento (**Relative
    Gap**, %). + **Angular Tolerance**.
  - *Distance (Absolute)* — separa por distância fixa (**Absolute Gap**). + **Angular Tolerance**.
  - *Max Lines* — no máximo N linhas, sem fundir direções muito diferentes. + **Angular Tolerance**.
- As demais opções (Merge Distance, Shape, Thickness, Output) são as mesmas do Cleanup
  Lines e se aplicam a **cada** linha gerada (cada uma com sua espessura média).

### Como funciona (sem SciPy)

Reimplementa o *Single-Line Fit* e o *Multi-Line (Cluster) Fit* do nijiGPen sem nenhuma
dependência pesada (`solvers/line_fit.py` + `operators/operator_cleanup.py`):

1. **Triangulação Delaunay** dos pontos do rascunho (`mathutils.geometry`, nativo).
2. **Árvore geradora mínima** euclidiana (Prim, Python puro) — substitui `scipy.sparse.csgraph`.
3. **Caminho mais longo** na árvore (BFS duplo) = a "espinha" que melhor representa a linha.
4. **Offset ao centroide** dos pontos vizinhos (`mathutils.kdtree`) — é o passo que **funde os
   traços próximos** num único centro.
5. **Suavização + reamostragem** (Laplaciano + Chaikin + por comprimento de arco) —
   substitui o B-spline de `scipy.interpolate`.

A **clusterização** (Multi) também dispensa o `scipy.cluster.hierarchy`. O critério padrão
**Overlap (cobertura)** funde dois traços só se uma fração grande de um corre dentro de uma
distância do outro — isso evita o "chaining" do *single-linkage* (em um desenho conectado,
todo traço encosta em algum vizinho e o limiar acaba fundindo tudo numa linha só). Os
critérios por distância usam *single-linkage*, que equivale aos **componentes conexos** do
grafo de proximidade (um **union-find**). Toda a similaridade usa só `mathutils.kdtree` e numpy.

**Preservar a forma:** um cluster de **um único traço** mantém os próprios pontos (sem
re-derivar espinha nem offset ao centroide, que achatariam a curva) — só apara pontas e
suaviza de leve. O offset ao centroide (que funde) só roda quando há vários traços. A
espessura uniforme automática usa o **percentil 80** do raio do rascunho (não a média), pra
a linha única não sair mais fina que o traço empilhado original.

## Por que é leve (sem dependências)

Este addon reaproveita o **core** do nijiGPen — principalmente a camada de compatibilidade
`api_router.py` (GPv2 ↔ GPv3, que faz a API nova de curvas do Blender 5.0 parecer a API
antiga de strokes) e os utilitários de geometria/cor em `utils.py`.

A detecção de regiões **não** usa SciPy, PyClipper, scikit-image nem Triangle. Como a matte
preenche todas as regiões com **uma única cor** (sem "hints" por região), o passo de
max-flow/labeling do SmartFill original — que exigia SciPy — desaparece. Sobra um pipeline
100% nativo:

1. **Triangulação** do line art via `mathutils.geometry.delaunay_2d_cdt` (nativo).
2. **Detecção de regiões** em Python puro: os triângulos são agrupados em regiões por
   componentes conexos usando apenas arestas que **não** são traço (union-find). Cada região
   é uma área chapada delimitada pelos traços. A região **exterior** é semeada
   geometricamente (a região do triângulo mais à esquerda, sempre no contorno externo), e um
   BFS no grafo de adjacência das regiões conta quantos traços separam cada região do exterior.
   - **Keep Holes ligado** → regra par/ímpar: regiões a uma profundidade ímpar são
     preenchidas, então o espaço negativo (anéis/janelas) fica vazio.
   - **Keep Holes desligado** → toda região cercada é preenchida sólida (à prova de bala em
     line art bagunçado/sobreposto).
3. **Traçado das arestas de borda** em loops fechados, classificados por área em contorno
   externo (fill) ou buraco (holdout).

Trabalhar com regiões inteiras (em vez de paridade por triângulo) elimina os artefatos de
"tabuleiro de xadrez" e o preenchimento invertido (preencher o vão entre dois desenhos) que
traços sobrepostos causavam.

Única dependência: `numpy`, que já vem embutido no Blender.

## Origem

Derivado do [nijiGPen](https://github.com/chsh2/nijiGPen) (GPL). A ideia anterior de "balde
de tinta" interativo foi descartada; este addon reaproveita o núcleo para um fluxo de matte
automático e determinístico.
