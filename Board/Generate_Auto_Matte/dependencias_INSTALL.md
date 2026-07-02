# Dependências do Cleanup (Ink)

O modo **Cleanup Lines (Ink)** usa `scipy` + `scikit-image` para o pipeline de esqueleto
(rasteriza a tinta → afina até a linha central → decompõe em galhos). Elas ficam numa pasta
`dependencias/` **dentro deste addon** (não versionada no git por causa do tamanho, ~238MB).

Se a pasta `dependencias/` não existir (ex.: clone novo do repo), reinstale com o **Python do
próprio Blender** para casar a versão (3.11) e o ABI do numpy (1.26):

```bash
BPY="<caminho do blender>/5.0/python/bin/python3.11"
uv pip install --python "$BPY" --target "dependencias" "scipy>=1.11,<1.14" "scikit-image>=0.22,<0.25"
```

(ou `"$BPY" -m pip install --target dependencias ...` se preferir pip.)

Sem essas dependências, o Cleanup (Ink) cai automaticamente num afinamento **Zhang-Suen em
numpy puro** (menor qualidade, mas funciona). Os modos legados (Cleanup Lines / Multi) não
precisam de nada além do numpy que já vem no Blender.
