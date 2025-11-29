import time
import psutil
import subprocess
import os
import sqlite3
import winreg
import ctypes
from ctypes import wintypes
from obsws_python.reqs import ReqClient
import re
import json  # <--- Necessário para ler Epic Games

# ================= CONFIGURAÇÕES =================
NOME_CENA_PRINCIPAL = "Cena"
NOME_FONTE_GAME_CAPTURE = "Captura de jogo"
NOME_FONTE_MIC = "Mic/Aux"
NOME_FONTE_DESKTOP = "Áudio do desktop"
FONTES_SEGURAS = ["Webcam", "Moldura", "AlertBox"]

OBS_PATH = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
OBS_DIR = r"C:\Program Files\obs-studio\bin\64bit"
OBS_WS_HOST = "localhost"
OBS_WS_PORT = 4455
OBS_WS_PASSWORD = "5PMSR7bYGPFGrNyE"
BASE_OUTPUT_DIR = r"C:\Users\david\Videos\Jogos - OBS"

DB_NAME = r"C:\Users\david\Documentos\Meus Scripts inicializaveis\jogos_obs.db"
VERIFICACOES_QTD = 10
VERIFICACOES_INTERVALO = 2
INTERVALO_MONITORAMENTO_TITULO = 5 

# ================= BANCO DE DADOS =================

def conectar_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jogos (
            appid TEXT PRIMARY KEY,
            nome TEXT,
            executavel TEXT,
            diretorio_instalacao TEXT,
            usar_mic INTEGER DEFAULT 0,
            origem TEXT DEFAULT 'Steam' 
        )
    ''')
    # Adiciona coluna 'origem' se não existir (para compatibilidade com DB antigo)
    try:
        cursor.execute("ALTER TABLE jogos ADD COLUMN origem TEXT DEFAULT 'Steam'")
    except:
        pass
    conn.commit()
    return conn

def buscar_executavel_provavel(diretorio):
    """Varredura de segurança caso o manifesto não indique o exe corretamente"""
    executaveis = []
    if not os.path.exists(diretorio):
        return "CONFIGURAR_MANUALMENTE.exe"

    for root, dirs, files in os.walk(diretorio):
        for file in files:
            if file.lower().endswith(".exe"):
                lixo = ["uninstall", "handler", "redist", "unitycrash", "laucher", "crashreport", "prereq"]
                if any(x in file.lower() for x in lixo):
                    continue
                path_completo = os.path.join(root, file)
                try:
                    tamanho = os.path.getsize(path_completo)
                    executaveis.append((file, tamanho))
                except:
                    pass
    executaveis.sort(key=lambda x: x[1], reverse=True)
    if executaveis:
        return executaveis[0][0]
    return "CONFIGURAR_MANUALMENTE.exe"

# ================= INTEGRAÇÃO STEAM =================

def encontrar_caminho_steam():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        return path
    except:
        return None

def sincronizar_steam_db():
    print("--- Sincronizando Steam... ---")
    steam_path = encontrar_caminho_steam()
    if not steam_path: return

    APPIDS_IGNORADOS = ["228980", "250820", "413080", "413090"]
    steamapps_paths = [os.path.join(steam_path, "steamapps")]
    
    # Busca bibliotecas extras
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                conteudo = f.read()
                caminhos = re.findall(r'"path"\s+"(.*?)"', conteudo)
                for c in caminhos:
                    c = c.replace("\\\\", "\\")
                    path_extra = os.path.join(c, "steamapps")
                    if path_extra not in steamapps_paths and os.path.exists(path_extra):
                        steamapps_paths.append(path_extra)
        except: pass

    conn = conectar_db()
    cursor = conn.cursor()
    novos = 0

    for library in steamapps_paths:
        if not os.path.exists(library): continue
        for file in os.listdir(library):
            if file.endswith(".acf"):
                try:
                    with open(os.path.join(library, file), 'r', encoding='utf-8', errors='ignore') as f:
                        data = f.read()
                        nome_match = re.search(r'"name"\s+"(.*?)"', data)
                        install_match = re.search(r'"installdir"\s+"(.*?)"', data)
                        appid_match = re.search(r'"appid"\s+"(.*?)"', data)

                        if nome_match and install_match and appid_match:
                            nome = nome_match.group(1)
                            pasta = install_match.group(1)
                            appid = appid_match.group(1)
                            
                            if appid in APPIDS_IGNORADOS: continue
                            if "redistributables" in nome.lower() or "soundtrack" in nome.lower(): continue

                            cursor.execute("SELECT nome FROM jogos WHERE appid = ?", (appid,))
                            if cursor.fetchone(): continue

                            dir_jogo = os.path.join(library, "common", pasta)
                            exe_nome = buscar_executavel_provavel(dir_jogo)

                            cursor.execute('''
                                INSERT INTO jogos (appid, nome, executavel, diretorio_instalacao, usar_mic, origem)
                                VALUES (?, ?, ?, ?, 0, 'Steam')
                            ''', (appid, nome, exe_nome, dir_jogo))
                            novos += 1
                            print(f"[Steam] Novo: {nome} -> {exe_nome}")
                except: pass
    conn.commit()
    conn.close()
    if novos > 0: print(f"Steam: {novos} novos jogos.")

# ================= INTEGRAÇÃO EPIC GAMES =================

def sincronizar_epic_db():
    print("--- Sincronizando Epic Games... ---")
    # Caminho padrão dos manifestos da Epic
    program_data = os.environ.get('ProgramData', 'C:\\ProgramData')
    manifests_path = os.path.join(program_data, "Epic", "EpicGamesLauncher", "Data", "Manifests")

    if not os.path.exists(manifests_path):
        print("Epic Games Launcher não encontrado (Pasta Manifests inexistente).")
        return

    conn = conectar_db()
    cursor = conn.cursor()
    novos = 0

    for file in os.listdir(manifests_path):
        if file.endswith(".item"):
            try:
                full_path = os.path.join(manifests_path, file)
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Extração de dados do JSON da Epic
                    nome = data.get("DisplayName")
                    install_loc = data.get("InstallLocation")
                    exe_path = data.get("LaunchExecutable") # Pode ser relativo (Binaries/Win64/Game.exe)
                    app_id = data.get("InstallationGuid") # Usaremos GUID como ID
                    
                    # Filtra Unreal Engine (não é jogo)
                    if "Unreal Engine" in nome:
                        continue

                    # Verifica se já existe
                    cursor.execute("SELECT nome FROM jogos WHERE appid = ?", (app_id,))
                    if cursor.fetchone(): continue

                    # Define o executável
                    nome_executavel = ""
                    if exe_path:
                        nome_executavel = os.path.basename(exe_path)
                    else:
                        # Se o manifesto não apontar o exe, escaneia a pasta
                        nome_executavel = buscar_executavel_provavel(install_loc)

                    cursor.execute('''
                        INSERT INTO jogos (appid, nome, executavel, diretorio_instalacao, usar_mic, origem)
                        VALUES (?, ?, ?, ?, 0, 'Epic')
                    ''', (app_id, nome, nome_executavel, install_loc))
                    
                    novos += 1
                    print(f"[Epic] Novo: {nome} -> {nome_executavel}")

            except Exception as e:
                print(f"Erro ao ler manifesto Epic {file}: {e}")

    conn.commit()
    conn.close()
    if novos > 0: print(f"Epic Games: {novos} novos jogos.")


def carregar_jogos_do_banco():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT nome, executavel, usar_mic FROM jogos")
    rows = cursor.fetchall()
    conn.close()
    lista_jogos = {}
    for row in rows:
        nome, exe, mic = row
        if exe and exe != "CONFIGURAR_MANUALMENTE.exe":
             lista_jogos[nome] = {"exe": exe, "mic": bool(mic)}
    return lista_jogos

# ================= FUNÇÕES DE SISTEMA =================

def processo_encontrado(nome_do_executavel):
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.info['name'] and nome_do_executavel.lower() in proc.info['name'].lower():
                return proc.info['pid']
        except:
            pass
    return None

def obter_info_janela_real(pid_alvo):
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    dados_janela = None 

    def enum_windows_callback(hwnd, _):
        nonlocal dados_janela
        if user32.IsWindowVisible(hwnd):
            pid_janela = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_janela))
            if pid_janela.value == pid_alvo:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width < 300 or height < 300: return True 

                length = user32.GetWindowTextLengthW(hwnd)
                buff_titulo = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff_titulo, length + 1)
                titulo = buff_titulo.value

                buff_class = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buff_class, 256)
                classe = buff_class.value

                if titulo and classe:
                    dados_janela = (titulo, classe)
                    return False 
        return True 

    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return dados_janela

def aguardar_estabilidade_inicial(pid, nome_jogo):
    print(f"\n[{nome_jogo}] Aguardando janela gráfica...")
    for i in range(1, VERIFICACOES_QTD + 1):
        time.sleep(VERIFICACOES_INTERVALO)
        if not psutil.pid_exists(pid): return None
        info = obter_info_janela_real(pid)
        if info:
            print(f"[{nome_jogo}] Janela detectada: '{info[0]}'")
            return info
    return None

# ================= OBS CONTROLE =================

def iniciar_obs():
    if not processo_encontrado("obs64.exe"):
        subprocess.Popen([OBS_PATH], cwd=OBS_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        print("Iniciando OBS...")
        time.sleep(8) 

def conectar_obs():
    try:
        return ReqClient(host=OBS_WS_HOST, port=OBS_WS_PORT, password=OBS_WS_PASSWORD)
    except:
        return None

def priorizar_visibilidade_jogo(ws):
    try:
        lista = ws.get_scene_item_list(NOME_CENA_PRINCIPAL).scene_items
        topo = len(lista) - 1 if lista else 0
        found = False
        for item in lista:
            if item['sourceName'].lower() == NOME_FONTE_GAME_CAPTURE.lower():
                ws.set_scene_item_enabled(NOME_CENA_PRINCIPAL, item['sceneItemId'], True)
                ws.set_scene_item_index(NOME_CENA_PRINCIPAL, item['sceneItemId'], topo)
                found = True
            elif item['sourceName'] not in FONTES_SEGURAS and item['sceneItemEnabled']:
                ws.set_scene_item_enabled(NOME_CENA_PRINCIPAL, item['sceneItemId'], False)
        if found: print(f"VISUAL: Fonte '{NOME_FONTE_GAME_CAPTURE}' trazida para frente.")
    except: pass

def sanitizar_string_janela(titulo, classe, executavel):
    """
    Remove ':' do título para evitar que o OBS confunda com o separador de campos.
    """
    if ":" in titulo:
        novo_titulo = titulo.split(":")[0].strip()
        print(f"DEBUG: Título com ':' detectado. Cortando para: '{novo_titulo}'")
        return f"{novo_titulo}:{classe}:{executavel}", 2 
    return f"{titulo}:{classe}:{executavel}", 1

def configurar_ambiente_gravacao(ws, jogo_atual, configs, info_janela):
    try:
        titulo, classe = info_janela
        executavel = configs["exe"]
        
        path = os.path.join(BASE_OUTPUT_DIR, jogo_atual)
        os.makedirs(path, exist_ok=True)
        ws.set_record_directory(path)

        ws.set_input_mute(NOME_FONTE_MIC, not configs["mic"])
        ws.set_input_mute(NOME_FONTE_DESKTOP, False)

        janela_string, prioridade = sanitizar_string_janela(titulo, classe, executavel)
        
        settings = {
            "capture_mode": "window", 
            "window": janela_string, 
            "priority": prioridade
        }
        ws.set_input_settings(NOME_FONTE_GAME_CAPTURE, settings, overlay=True)
        
        priorizar_visibilidade_jogo(ws)
        print(f"OBS Configurado | Alvo: {janela_string} | Prioridade: {prioridade}")
        return titulo 
    except Exception as e:
        print(f"Erro config OBS: {e}")
        return None

def atualizar_rastreamento_janela(ws, executavel, info_janela):
    try:
        titulo, classe = info_janela
        janela_string, prioridade = sanitizar_string_janela(titulo, classe, executavel)
        settings = {"capture_mode": "window", "window": janela_string, "priority": prioridade}
        ws.set_input_settings(NOME_FONTE_GAME_CAPTURE, settings, overlay=True)
        print(f"ATUALIZAÇÃO: Novo alvo -> {titulo}")
    except:
        pass

def iniciar_gravacao(ws):
    ws.start_record()
    print(">>> GRAVAÇÃO INICIADA <<<")

def parar_gravacao(ws):
    ws.stop_record()
    print(">>> GRAVAÇÃO PARADA <<<")

# ================= MAIN =================
                
def main():
    # Sincroniza ambas as plataformas
    sincronizar_steam_db()
    sincronizar_epic_db()
    
    lista_jogos_db = carregar_jogos_do_banco()
    print(f"Monitorando {len(lista_jogos_db)} jogos (Steam + Epic).")

    gravando = False
    ws = None
    nome_jogo_atual = None
    pid_atual = None
    titulo_janela_atual = None
    configs_atual = None
    ultimo_monitoramento = 0
    
    while True:
        if gravando and nome_jogo_atual:
            if psutil.pid_exists(pid_atual):
                if time.time() - ultimo_monitoramento > INTERVALO_MONITORAMENTO_TITULO:
                    nova_info = obter_info_janela_real(pid_atual)
                    if nova_info and nova_info[0] != titulo_janela_atual:
                        atualizar_rastreamento_janela(ws, configs_atual["exe"], nova_info)
                        titulo_janela_atual = nova_info[0]
                    ultimo_monitoramento = time.time()
            else:
                print(f"Processo de {nome_jogo_atual} encerrado.")
                if ws:
                    try: parar_gravacao(ws)
                    except: pass
                gravando = False
                nome_jogo_atual = None
                pid_atual = None
                lista_jogos_db = carregar_jogos_do_banco() # Recarrega DB caso tenha edição manual
                print("Aguardando novo jogo...")
        
        else:
            for nome_jogo, configs in lista_jogos_db.items():
                pid = processo_encontrado(configs["exe"])
                if pid:
                    print(f"\nDetectado: {nome_jogo} (PID: {pid})")
                    info_janela = aguardar_estabilidade_inicial(pid, nome_jogo)
                    
                    if info_janela:
                        iniciar_obs()
                        if ws is None: ws = conectar_obs()
                        if ws:
                            titulo_usado = configurar_ambiente_gravacao(ws, nome_jogo, configs, info_janela)
                            time.sleep(2)
                            iniciar_gravacao(ws)
                            
                            gravando = True
                            nome_jogo_atual = nome_jogo
                            pid_atual = pid
                            titulo_janela_atual = titulo_usado 
                            configs_atual = configs
                            ultimo_monitoramento = time.time()
                    break 
        time.sleep(3)

if __name__ == "__main__":
    main()