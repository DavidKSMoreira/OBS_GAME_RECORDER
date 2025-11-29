# OBS_GAME_RECORDER

GUIA DE USUÁRIO: OBS AUTO RECORDER MANAGER
Versão: 3.0 (Pro Manager)

Este guia auxilia na instalação, configuração e uso do sistema de gravação 
automática de jogos utilizando o OBS Studio.

------------------------------------------------------------------------------
1. PRÉ-REQUISITOS (ANTES DE INSTALAR)
------------------------------------------------------------------------------
Para que o software funcione corretamente, o seu OBS Studio precisa estar 
configurado de uma maneira específica, pois o robô envia comandos para fontes
com nomes exatos.

1.1. Configuração do WebSocket no OBS:
   - Abra o OBS Studio.
   - Vá em "Ferramentas" > "Configurações do Servidor WebSocket".
   - Marque "Habilitar servidor WebSocket".
   - Porta do Servidor: 4455 (Padrão).
   - Senha: Defina uma senha (ex: 123456) ou anote a senha existente. 
     Você precisará dela durante a instalação.

1.2. Configuração das Cenas e Fontes:
   O programa busca por duas fontes específicas na sua cena. Você DEVE criar 
   ou renomear suas fontes para EXATAMENTE os nomes abaixo (respeitando maiúsculas):
   
   A) Fonte de Vídeo:
      - Nome: "Captura de jogo"
      - Tipo: Adicione uma fonte do tipo "Captura de Jogo" (Game Capture).
   
   B) Fonte de Áudio (Microfone):
      - Nome: "Mic/Aux"
      - Nota: Geralmente é o nome padrão, mas verifique no Mixer de Áudio.

------------------------------------------------------------------------------
2. INSTALAÇÃO
------------------------------------------------------------------------------
O arquivo "Instalador_OBS_Recorder.exe" fará toda a configuração inicial.

PASSO A PASSO:
1. Clique com o botão direito no "Instalador_OBS_Recorder.exe".
2. Selecione "Executar como Administrador" (Necessário para criar pastas no C:\).
3. Siga as instruções na tela preta (terminal):
   
   - Passo 1 (Onde instalar): Pressione Enter para aceitar o padrão (C:\OBS_Auto_Recorder).
   - Passo 2 (Localizar OBS): O instalador tentará achar o OBS automaticamente. 
     Se achar, digite 'S'. Se não, cole o caminho do "obs64.exe".
   - Passo 3 (Pasta de Vídeos): Onde as gravações serão salvas.
   - Passo 4 (Senha WebSocket): Digite a mesma senha configurada no item 1.1 deste guia.

4. Ao finalizar, uma pasta será aberta contendo o arquivo "INICIAR_GRAVADOR.bat".
   Use este arquivo para abrir o programa daqui para frente.

------------------------------------------------------------------------------
3. COMO USAR O PROGRAMA (OBS RECORDER)
------------------------------------------------------------------------------
Abra o software através do atalho "INICIAR_GRAVADOR.bat".

INTERFACE - ABA DASHBOARD:
- Status: Mostra se o robô de monitoramento está ativo.
- Botão "INICIAR SERVIÇO": Clique aqui para começar a monitorar.
  [!] O programa só grava se o status estiver "RODANDO" (Verde).
- Logs: Mostra em tempo real o que o robô está fazendo (ex: "Jogo detectado", "Gravando").

INTERFACE - ABA MEUS JOGOS:
- Rastrear Jogos Automaticamente:
  Clique neste botão para varrer seu PC em busca de jogos instalados via Steam ou Epic Games.
  O processo pode levar alguns segundos.
- Lista de Jogos:
  Mostra os jogos cadastrados.
  - Coluna "Mic": Indica se o microfone será gravado naquele jogo.
  - Duplo Clique: Clique duas vezes em um jogo na lista para ativar/desativar o microfone para ele.

INTERFACE - ABA ADICIONAR MANUALMENTE:
Use esta aba para jogos piratas, emuladores ou jogos fora da Steam/Epic.
1. Nome do Jogo: Como a pasta do vídeo será nomeada.
2. Executável: Busque o arquivo .exe do jogo (ex: GTA5.exe).
3. Gravar Microfone: Marque se deseja capturar sua voz neste jogo.
4. Clique em "CADASTRAR JOGO".

INTERFACE - CONFIGURAÇÕES:
Use esta aba caso mude a senha do OBS, reinstale o OBS em outro local ou queira
mudar a pasta de destino dos vídeos.

------------------------------------------------------------------------------
4. FUNCIONAMENTO AUTOMÁTICO
------------------------------------------------------------------------------
1. Abra o OBS Auto Recorder e clique em "INICIAR SERVIÇO".
2. Abra seu jogo.
3. O software detectará o processo do jogo (se estiver cadastrado na lista).
4. Se o OBS estiver fechado, o software abrirá o OBS automaticamente.
5. A gravação iniciará sozinha. O ícone do OBS na barra de tarefas mostrará a "bolinha vermelha".
6. Ao fechar o jogo, a gravação para automaticamente após 3 segundos.

------------------------------------------------------------------------------
5. RESOLUÇÃO DE PROBLEMAS (TROUBLESHOOTING)
------------------------------------------------------------------------------

PROBLEMA: O jogo abriu, mas não começou a gravar.
SOLUÇÃO: 
1. Verifique na aba Dashboard se o serviço está "RODANDO".
2. Verifique se a senha do WebSocket está correta na aba Configurações.
3. No OBS, verifique se a fonte de vídeo se chama exatamente "Captura de jogo".

PROBLEMA: O OBS abre, mas a tela fica preta na gravação.
SOLUÇÃO:
O programa tenta ajustar a captura para a janela específica, mas alguns jogos 
exigem que o OBS seja executado como Administrador.
- Feche o OBS e o Gravador.
- Abra o OBS manualmente como Administrador.
- Abra o Gravador e inicie o serviço.

PROBLEMA: O instalador fecha imediatamente.
SOLUÇÃO:
Execute o instalador via CMD ou PowerShell para ver a mensagem de erro, ou 
certifique-se de que está rodando como Administrador.

------------------------------------------------------------------------------
Desenvolvido via Automação Python + OBS WebSocket
------------------------------------------------------------------------------
