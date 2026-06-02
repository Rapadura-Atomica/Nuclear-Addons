# Generate Auto Matte

Addon de Grease Pencil para Blender (4.3+ / 5.0) focado em quem trabalha com **board / storyboard**.

Com um clique, ele preenche **todas as regiões fechadas** do seu line art com uma cor chapada (cinza por padrão) numa camada dedicada chamada **`AutoMatte`**, posicionada atrás do desenho.

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
