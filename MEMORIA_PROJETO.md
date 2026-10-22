# Referência para retomar o projeto

## Programa

- Repositório: `Zanardi-04/programa`, branch `main`.
- Aplicativo desktop offline de consulta de endereços, áreas e oficiais.
- Código e dados: `Consulta_Enderecos_Oficiais/`.
- Linguagem: Python 3.11 ou superior, com Tkinter.
- O usuário utiliza Windows e já conseguiu baixar o ZIP pelo GitHub e gerar o executável.

## Preferências confirmadas

- Visual azul escuro inspirado na referência enviada pelo usuário, com panorama do Rio de Janeiro.
- Não incluir o botão “Ler mandado”: essa função não existe no programa.
- Preservar as regras de consulta, dados, histórico CSV e exportação TXT.
- Manter as funções de áreas, oficiais e informações do programa.
- A versão visual refinada inclui botões arredondados, ícones suaves, fontes maiores e indicadores PRONTO, LOCALIZADO e CONFERIR.
- Atalhos atuais: Enter para consultar, Ctrl+L para buscar e Esc para limpar.

## Entrega e execução

- Pacote atual: `distribuicao/Consulta_Enderecos_Layout_Azul_v2.zip`.
- Prévia: `docs/previa-layout-v2.png`.
- A versão anterior permanece em `distribuicao/Consulta_Enderecos_Layout_Azul.zip`.
- Links internos do ambiente e links `sandbox:` não funcionaram para download nesta interface.
- O usuário conseguiu baixar abrindo o ZIP no GitHub e clicando na seta **Download raw file**, entre os ícones de copiar e editar.
- Para instalar uma atualização: extrair em uma pasta nova, preservar ajustes/histórico e bases personalizadas, e executar `CRIAR_EXE_NO_WINDOWS.bat` no Windows.
- Executável gerado: `dist\ConsultaEnderecos\ConsultaEnderecos.exe`.
- Manter a pasta `recursos` junto do aplicativo; o `.bat` a copia para a distribuição.

## Validação já realizada

- Suíte original de regressão passou com 1.491 registros carregados.
- Interface, consultas, histórico CSV, exportação TXT e janelas auxiliares foram validados em Linux com tela virtual.
- A versão 2 também foi testada depois da extração do próprio ZIP, incluindo os recursos visuais.
- A geração do executável e o ajuste da barra de título nativa do Windows não foram executados neste ambiente Linux.

Este arquivo registra o contexto do projeto. Ele não representa uma memória automática do assistente entre conversas; pode ser consultado para retomar o trabalho.
