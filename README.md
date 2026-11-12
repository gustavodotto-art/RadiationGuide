# Radiation Guide 2.0.0-rc1

Protótipo experimental para extração local de metadados de dose de tomografia computadorizada e revisão técnica. Código distribuído sob a licença MIT; consulte [LICENSE](LICENSE).

## Instalação e uso

Consulte [LEIA_ME_WINDOWS.txt](LEIA_ME_WINDOWS.txt) e [LEIA_ME.txt](LEIA_ME.txt). O pacote contém código Python e um iniciador para Windows 10/11; não é um executável nativo e a instalação nesses sistemas ainda requer teste. É necessário Python 3.10 a 3.13. A primeira execução precisa de internet para instalar as dependências; a análise posterior ocorre localmente em `http://127.0.0.1:5050`.

Extraia o pacote ou clone o repositório e execute `ABRIR_WINDOWS.bat`. Em outro sistema, execute `python3 INICIAR.py` com Python compatível. Mantenha o terminal aberto; encerre com Ctrl+C.

## Escopo e limites

Importa ZIP ou DICOM único de TC, prioriza RDSR e usa cabeçalhos CT quando possível. Apresenta CTDIvol, DLP e SSDE somente quando há metadados compatíveis. Não estima dose por órgão ou dose efetiva. Os gatilhos operacionais não são avaliações individuais de conformidade com níveis de referência diagnósticos (DRL). Não há IA externa, modelo preditivo ou integração de escrita no PACS.

Os resultados ausentes permanecem indisponíveis. A extração de dose de imagens, OCR, campos privados de fabricantes e campos Enhanced CT presentes somente em grupos funcionais não está validada. Acurácia clínica dosimétrica e instalação em Windows ainda não foram estabelecidas. O protótipo não substitui revisão profissional.

## Privacidade

Este repositório não contém exames ou dados de pacientes, bancos de dados, chaves locais ou credenciais. Os testes geram metadados fictícios em tempo de execução. Leia [PRIVACY.md](PRIVACY.md) antes de importar dados reais. Nunca inclua exames, relatórios clínicos, bancos ou chaves em commits, issues ou mensagens de feedback.

## Testes

Em ambiente isolado, instale `requirements.txt` e `requirements-dev.txt`, depois execute `python -m pytest`. Foram aprovados 42 testes automatizados em Python 3.12/macOS. Os testes cobrem comportamento de software com dados sintéticos; não demonstram acurácia clínica. Consulte [ALTERACOES_E_VALIDACAO.txt](ALTERACOES_E_VALIDACAO.txt) e [ROTEIRO_TESTE_E_FEEDBACK.txt](ROTEIRO_TESTE_E_FEEDBACK.txt).

## Licença e componentes

Copyright (c) 2026 Radiation Guide contributors. A licença MIT consta em LICENSE. Dependências são instaladas separadamente e mantêm suas próprias licenças. A publicação na conta vinculada à UFSM não declara homologação ou aprovação institucional.
