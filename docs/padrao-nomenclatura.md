# Padrão de nomenclatura dos arquivos

```
EMPRESA_BANCO_CONTA_COMPETENCIA_TIPO.ext
```

- **EMPRESA**: código curto da empresa (ex: `DPA`).
- **BANCO**: nome do banco em maiúsculas, sem espaços/acentos (ex: `INTER`, `SANTANDER`, `SICOOB`).
- **CONTA**: número da conta corrente (sem agência, sem dígito separado por espaço).
- **COMPETENCIA**: mês/ano + quinzena, no formato `MM-AAAA-Q1` ou `MM-AAAA-Q2`.
  - `Q1` = extrato do dia 01 ao dia 15 do mês.
  - `Q2` = extrato do dia 16 ao último dia do mês.
  - O arquivo é arquivado na pasta do **mês a que a quinzena pertence**, independentemente do dia em que o download foi feito.
- **TIPO**: `PDF`, `OFX` ou `EXCEL`.

## Exemplos

```
DPA_INTER_12345_08-2026-Q1_PDF.pdf
DPA_INTER_12345_08-2026-Q1_OFX.ofx
DPA_SANTANDER_67890_08-2026-Q2_EXCEL.xlsx
```

## Regra de não sobrescrita

Antes de gravar qualquer arquivo, a automação verifica se já existe um arquivo com o mesmo nome padronizado na pasta de destino:

- Se **não existe** → salva normalmente.
- Se **existe e o conteúdo é idêntico** (mesmo tamanho/hash) → não duplica, apenas registra no log como "já existente".
- Se **existe mas o conteúdo é diferente** → **não sobrescreve**. Salva a nova versão com sufixo `_v2`, `_v3`... e sinaliza no relatório final para conferência manual.

## Calendário de execução

| Disparo | Período baixado | Sufixo de competência |
|---|---|---|
| Dia 16 de cada mês | dia 01 a 15 do mês corrente | `MM-AAAA-Q1` |
| Dia 01 de cada mês | dia 16 ao último dia do mês anterior | `MM-AAAA-Q2` (mês anterior) |
