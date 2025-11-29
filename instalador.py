import os
import sys
import json
import shutil
import subprocess
import ctypes

def is_admin():
    """Verifica privilégios de administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def resource_path(relative_path):
    """
    Função CRÍTICA para encontrar arquivos quando empacotados pelo PyInstaller.
    Quando vira .exe, os arquivos ficam numa pasta temporária sys._MEIPASS.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def encontrar_obs_automaticamente():
    caminhos_padrao = [
        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe"
    ]
    for caminho in caminhos_padrao:
        if os.path.exists(caminho):
            return caminho
    return None

def instalar():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*50)
    print("   INSTALADOR: OBS AUTO RECORDER MANAGER")
    print("="*50)

    # 1. Verificar Admin
    if not is_admin():
        print("\n[!] AVISO: Execute como Administrador para evitar erros de permissão.\n")
        input("Pressione Enter para tentar continuar ou feche e reabra como Admin...")

    # 2. Definir Diretório
    print("\n--- PASSO 1: Onde instalar o programa? ---")
    padrao_inst = r"C:\OBS_Auto_Recorder"
    dir_install = input(f"Caminho [Padrão: {padrao_inst}]: ").strip()
    if not dir_install: dir_install = padrao_inst

    # 3. Localizar OBS
    print("\n--- PASSO 2: Localizar OBS Studio ---")
    obs_path = encontrar_obs_automaticamente()
    if obs_path:
        print(f"OBS detectado: {obs_path}")
        if input("Correto? (S/N): ").lower() != 's': obs_path = None
            
    if not obs_path:
        obs_path = input("Caminho do obs64.exe: ").strip().replace('"', '')

    # 4. Diretório Vídeos
    print("\n--- PASSO 3: Pasta de Vídeos ---")
    home = os.path.expanduser("~")
    padrao_video = os.path.join(home, "Videos", "GameRecordings")
    dir_video = input(f"Caminho [Padrão: {padrao_video}]: ").strip()
    if not dir_video: dir_video = padrao_video

    # 5. Senha WebSocket
    print("\n--- PASSO 4: Senha WebSocket OBS ---")
    ws_senha = input("Senha [Padrão: 123456]: ").strip() or "123456"

    print("\n[INSTALANDO...]")
    
    try:
        os.makedirs(dir_install, exist_ok=True)
        os.makedirs(dir_video, exist_ok=True)

        # Procuramos o executável empacotado dentro do instalador
        nome_executavel = "OBS_Recorder.exe"
        caminho_origem = resource_path(nome_executavel)
        caminho_destino = os.path.join(dir_install, nome_executavel)
        
        if os.path.exists(caminho_origem):
            shutil.copy2(caminho_origem, caminho_destino)
            print(f"[OK] Software principal instalado em: {caminho_destino}")
        else:
            print(f"[ERRO CRÍTICO] O arquivo {nome_executavel} não foi encontrado dentro do pacote!")
            print(f"Procurado em: {caminho_origem}")
            input("Pressione Enter para sair...")
            sys.exit()

        # Criar config.json
        config_data = {
            "obs_path": obs_path,
            "obs_dir": os.path.dirname(obs_path) if obs_path else "",
            "obs_ws_port": 4455,
            "obs_ws_password": ws_senha,
            "output_dir": dir_video,
            "db_name": os.path.join(dir_install, "jogos_obs.db")
        }
        with open(os.path.join(dir_install, "config.json"), 'w') as f:
            json.dump(config_data, f, indent=4)

        # Criar Atalho .bat
        bat_content = f'@echo off\ncd /d "{dir_install}"\nstart "" "{nome_executavel}"'
        bat_path = os.path.join(dir_install, "INICIAR_GRAVADOR.bat")
        with open(bat_path, 'w') as f:
            f.write(bat_content)
        
        print("[OK] Configuração e atalhos criados.")

    except Exception as e:
        print(f"\n[ERRO] Falha na instalação: {e}")
        input("Enter para sair...")
        sys.exit()

    print("\n" + "="*50)
    print("   INSTALAÇÃO CONCLUÍDA!")
    print("="*50)
    print(f"Pasta: {dir_install}")
    input("Pressione Enter para finalizar...")

if __name__ == "__main__":
    instalar()

    
