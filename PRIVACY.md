# Privacidade e armazenamento local

DICOMs são lidos transitoriamente. Identificadores de paciente e estudo são convertidos em pseudônimos por HMAC antes da gravação. Nomes, data de nascimento, UIDs originais e descrições livres não são persistidos nos registros e PDFs. As cópias temporárias de uploads são removidas após o processamento; o arquivo original selecionado pelo usuário permanece no computador.

Pseudonimização não é anonimização nem criptografia. O banco retém mês do exame, região e resultados técnicos, que continuam sensíveis. Banco e chave ficam em `_runtime_v2/data`; proteja o dispositivo e essa pasta. O protótipo não inclui controle institucional de acesso nem criptografia de banco. Não copie banco ou chave para este repositório.

O servidor escuta apenas em 127.0.0.1. A integração externa de IA foi removida. A instalação inicial baixa dependências; a análise não chama serviço externo. Estas medidas não estabelecem, por si, conformidade com LGPD nem dispensa de avaliação ética. O uso de exames reais exige as autorizações aplicáveis.

Para feedback, descreva o erro e a versão, sem exames, nomes, identificadores, datas completas, relatórios clínicos ou capturas com dados pessoais.
