import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import sqlite3
import os
import json
import time
import threading
import psutil
import subprocess
import winreg
import ctypes
import uuid
import re
from ctypes import wintypes
from obsws_python.reqs import ReqClient

# ================= CLASSE DE CONFIGURAÇÃO =================
class ConfigHandler:
    def __init__(self):
        self.file_name = "config.json"
        self.default_config = {
            "obs_path": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
            "obs_dir": r"C:\Program Files\obs-studio\bin\64bit",
            "obs_ws_port": 4455,
            "obs_ws_password": "insira_sua_senha_aqui",
            "output_dir": os.path.join(os.path.expanduser("~"), "Videos", "GameRecordings"),
            "db_name": "jogos_obs.db"
        }
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(self.file_name):
            self.save_config(self.default_config)
            return self.default_config
        try:
            with open(self.file_name, 'r') as f:
                return json.load(f)
        except:
            return self.default_config

    def save_config(self, new_config):
        self.config = new_config
        with open(self.file_name, 'w') as f:
            json.dump(new_config, f, indent=4)

# ================= BACKEND (LÓGICA DO SCRIPT PRINCIPAL PORTADA) =================
class AutomacaoBackend:
    def __init__(self, config_handler, log_callback):
        self.cfg_handler = config_handler
        self.log = log_callback
        self.running = False
        self.ws = None
        self.stop_event = threading.Event()
        
        # Constantes idênticas ao script de referência
        self.NOME_CENA = "Cena"
        self.NOME_FONTE_GAME = "Captura de jogo"
        self.NOME_FONTE_MIC = "Mic/Aux"
        self.NOME_FONTE_DESKTOP = "Áudio do desktop"
        self.FONTES_SEGURAS = ["Webcam", "Moldura", "AlertBox"]
        self.INTERVALO_MONITORAMENTO_TITULO = 5

    def log_msg(self, msg):
        if self.log:
            self.log(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def conectar_db(self):
        db_path = self.cfg_handler.config["db_name"]
        conn = sqlite3.connect(db_path)
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
        # Garante compatibilidade caso o DB já exista sem a coluna origem
        try:
            cursor.execute("ALTER TABLE jogos ADD COLUMN origem TEXT DEFAULT 'Steam'")
        except: pass
        conn.commit()
        return conn

    # --- VARREDURA E SCANNER (Lógica da Referência) ---
    def buscar_executavel_provavel(self, diretorio):
        executaveis = []
        if not os.path.exists(diretorio): return "CONFIGURAR_MANUALMENTE.exe"
        
        for root, _, files in os.walk(diretorio):
            for file in files:
                if file.lower().endswith(".exe"):
                    lixo = ["uninstall", "handler", "redist", "unitycrash", "laucher", "crashreport", "prereq"]
                    if any(x in file.lower() for x in lixo): continue
                    try:
                        tamanho = os.path.getsize(os.path.join(root, file))
                        executaveis.append((file, tamanho))
                    except: pass
        
        executaveis.sort(key=lambda x: x[1], reverse=True)
        return executaveis[0][0] if executaveis else "CONFIGURAR_MANUALMENTE.exe"

    def realizar_varredura_completa(self):
        self.log_msg("Iniciando varredura (Steam + Epic)...")
        conn = self.conectar_db()
        cursor = conn.cursor()
        novos_count = 0
        appids_ignorados = ["228980", "250820", "413080", "413090"]

        # 1. STEAM
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            steamapps_paths = [os.path.join(steam_path, "steamapps")]
            
            # Bibliotecas extras (libraryfolders.vdf)
            vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
            if os.path.exists(vdf_path):
                with open(vdf_path, 'r', encoding='utf-8', errors='ignore') as f:
                    conteudo = f.read()
                    caminhos = re.findall(r'"path"\s+"(.*?)"', conteudo)
                    for c in caminhos:
                        p_extra = os.path.join(c.replace("\\\\", "\\"), "steamapps")
                        if os.path.exists(p_extra) and p_extra not in steamapps_paths:
                            steamapps_paths.append(p_extra)

            for library in steamapps_paths:
                if not os.path.exists(library): continue
                for file in os.listdir(library):
                    if file.endswith(".acf"):
                        try:
                            with open(os.path.join(library, file), 'r', encoding='utf-8', errors='ignore') as f:
                                data = f.read()
                                nome = re.search(r'"name"\s+"(.*?)"', data)
                                install = re.search(r'"installdir"\s+"(.*?)"', data)
                                appid = re.search(r'"appid"\s+"(.*?)"', data)

                                if nome and install and appid:
                                    n, p, id_ = nome.group(1), install.group(1), appid.group(1)
                                    if id_ in appids_ignorados: continue
                                    if "redist" in n.lower() or "soundtrack" in n.lower(): continue
                                    
                                    cursor.execute("SELECT 1 FROM jogos WHERE appid = ?", (id_,))
                                    if cursor.fetchone(): continue

                                    dir_jogo = os.path.join(library, "common", p)
                                    exe = self.buscar_executavel_provavel(dir_jogo)
                                    
                                    cursor.execute("INSERT INTO jogos (appid, nome, executavel, diretorio_instalacao, origem) VALUES (?, ?, ?, ?, 'Steam')", 
                                                   (id_, n, exe, dir_jogo))
                                    novos_count += 1
                        except: pass
        except Exception as e:
            self.log_msg(f"Erro Steam: {e}")

        # 2. EPIC GAMES
        try:
            program_data = os.environ.get('ProgramData', 'C:\\ProgramData')
            manifests = os.path.join(program_data, "Epic", "EpicGamesLauncher", "Data", "Manifests")
            if os.path.exists(manifests):
                for file in os.listdir(manifests):
                    if file.endswith(".item"):
                        try:
                            with open(os.path.join(manifests, file), 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                nome = data.get("DisplayName")
                                if "Unreal Engine" in nome: continue
                                
                                id_ = data.get("InstallationGuid")
                                cursor.execute("SELECT 1 FROM jogos WHERE appid = ?", (id_,))
                                if cursor.fetchone(): continue
                                
                                install_loc = data.get("InstallLocation")
                                exe_path = data.get("LaunchExecutable")
                                exe = os.path.basename(exe_path) if exe_path else self.buscar_executavel_provavel(install_loc)
                                
                                cursor.execute("INSERT INTO jogos (appid, nome, executavel, diretorio_instalacao, origem) VALUES (?, ?, ?, ?, 'Epic')",
                                               (id_, nome, exe, install_loc))
                                novos_count += 1
                        except: pass
        except Exception as e:
            self.log_msg(f"Erro Epic: {e}")

        conn.commit()
        conn.close()
        return novos_count

    # --- SISTEMA E OBS (Lógica da Referência) ---
    def obter_info_janela(self, pid_alvo):
        # Lógica exata do script de referência com validação de tamanho < 300px
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        dados = None

        def callback(hwnd, _):
            nonlocal dados
            if user32.IsWindowVisible(hwnd):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == pid_alvo:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    # Filtro de tamanho para evitar janelas fantasmas
                    if (rect.right - rect.left) < 300 or (rect.bottom - rect.top) < 300: return True

                    length = user32.GetWindowTextLengthW(hwnd)
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    
                    buff_cls = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, buff_cls, 256)
                    
                    if buff.value and buff_cls.value:
                        dados = (buff.value, buff_cls.value)
                        return False
            return True
        user32.EnumWindows(WNDENUMPROC(callback), 0)
        return dados

    def iniciar_obs(self):
        obs_exe = self.cfg_handler.config["obs_path"].split("\\")[-1]
        processos = [p.info['name'] for p in psutil.process_iter(['name'])]
        if obs_exe not in processos:
            self.log_msg("Iniciando OBS Studio...")
            try:
                subprocess.Popen([self.cfg_handler.config["obs_path"]], 
                               cwd=self.cfg_handler.config["obs_dir"],
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                time.sleep(8)
            except Exception as e:
                self.log_msg(f"ERRO ao abrir OBS: {e}")

    def conectar_websocket(self):
        cfg = self.cfg_handler.config
        try:
            client = ReqClient(host='localhost', port=cfg["obs_ws_port"], password=cfg["obs_ws_password"])
            # self.log_msg("WebSocket conectado!")
            return client
        except:
            return None

    def sanitizar_janela(self, titulo, classe, exe):
        # Correção do problema dos dois pontos ":"
        if ":" in titulo:
            titulo = titulo.split(":")[0].strip()
            return f"{titulo}:{classe}:{exe}", 2
        return f"{titulo}:{classe}:{exe}", 1

    def priorizar_visibilidade_jogo(self, ws):
        # Traz a captura de jogo para frente
        try:
            lista = ws.get_scene_item_list(self.NOME_CENA).scene_items
            topo = len(lista) - 1 if lista else 0
            found = False
            for item in lista:
                if item['sourceName'].lower() == self.NOME_FONTE_GAME.lower():
                    ws.set_scene_item_enabled(self.NOME_CENA, item['sceneItemId'], True)
                    ws.set_scene_item_index(self.NOME_CENA, item['sceneItemId'], topo)
                    found = True
                elif item['sourceName'] not in self.FONTES_SEGURAS and item['sceneItemEnabled']:
                    ws.set_scene_item_enabled(self.NOME_CENA, item['sceneItemId'], False)
            if found: self.log_msg("Visual OBS organizado.")
        except: pass

    def aguardar_estabilidade(self, pid, nome_jogo):
        self.log_msg(f"Aguardando janela gráfica para {nome_jogo}...")
        for i in range(10): # Tenta por 20 segundos aprox (10 * 2)
            if self.stop_event.is_set(): return None
            time.sleep(2)
            if not psutil.pid_exists(pid): return None
            info = self.obter_info_janela(pid)
            if info:
                return info
        return None

    def loop_principal(self):
        self.log_msg("--- Serviço de Monitoramento Iniciado ---")
        while not self.stop_event.is_set():
            try:
                conn = self.conectar_db()
                cursor = conn.cursor()
                cursor.execute("SELECT nome, executavel, usar_mic FROM jogos")
                # Cria dicionário {executavel_lower: dados}
                jogos = {row[1].lower(): {"nome": row[0], "mic": row[2], "exe_real": row[1]} for row in cursor.fetchall()}
                conn.close()
            except: jogos = {}

            jogo_detectado = None
            pid_detectado = None

            # 1. Busca Processo
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() in jogos:
                        chave = proc.info['name'].lower()
                        jogo_detectado = jogos[chave]
                        pid_detectado = proc.info['pid']
                        break
                except: pass
            
            if jogo_detectado:
                nome_jogo = jogo_detectado['nome']
                self.log_msg(f"Processo detectado: {nome_jogo}")
                
                # 2. Aguarda Janela Estável
                info_janela = self.aguardar_estabilidade(pid_detectado, nome_jogo)
                
                if info_janela and not self.stop_event.is_set():
                    self.iniciar_obs()
                    self.ws = self.conectar_websocket()
                    
                    if self.ws:
                        # 3. Configuração Inicial da Gravação
                        titulo, classe = info_janela
                        janela_str, prioridade = self.sanitizar_janela(titulo, classe, jogo_detectado["exe_real"])
                        
                        path_video = os.path.join(self.cfg_handler.config["output_dir"], nome_jogo)
                        os.makedirs(path_video, exist_ok=True)
                        
                        try:
                            self.ws.set_record_directory(path_video)
                            
                            # Áudio
                            self.ws.set_input_mute(self.NOME_FONTE_MIC, not bool(jogo_detectado["mic"]))
                            self.ws.set_input_mute(self.NOME_FONTE_DESKTOP, False) # Garante desktop audio
                            
                            # Vídeo
                            settings = {"capture_mode": "window", "window": janela_str, "priority": prioridade}
                            self.ws.set_input_settings(self.NOME_FONTE_GAME, settings, overlay=True)
                            self.priorizar_visibilidade_jogo(self.ws)
                            
                            self.ws.start_record()
                            self.log_msg(f">>> GRAVANDO: {nome_jogo} (Janela: {titulo})")
                            
                            titulo_atual = titulo
                            ultimo_check_titulo = time.time()
                            
                            # 4. Loop de Gravação (Monitoramento Dinâmico)
                            while psutil.pid_exists(pid_detectado) and not self.stop_event.is_set():
                                time.sleep(2)
                                
                                # Verifica mudança de título (Menu -> Jogo)
                                if time.time() - ultimo_check_titulo > self.INTERVALO_MONITORAMENTO_TITULO:
                                    nova_info = self.obter_info_janela(pid_detectado)
                                    if nova_info and nova_info[0] != titulo_atual:
                                        t_novo, c_novo = nova_info
                                        j_str_novo, p_novo = self.sanitizar_janela(t_novo, c_novo, jogo_detectado["exe_real"])
                                        settings = {"capture_mode": "window", "window": j_str_novo, "priority": p_novo}
                                        self.ws.set_input_settings(self.NOME_FONTE_GAME, settings, overlay=True)
                                        self.log_msg(f"Atualizando alvo: {t_novo}")
                                        titulo_atual = t_novo
                                    ultimo_check_titulo = time.time()
                            
                            self.ws.stop_record()
                            self.log_msg("Gravação finalizada.")
                            time.sleep(3) # Respiro pós gravação
                            
                        except Exception as e:
                            self.log_msg(f"Erro OBS/WebSocket: {e}")
                            time.sleep(5)
            
            time.sleep(3) # Ciclo principal
        self.log_msg("Serviço parado.")

    def start(self):
        if not self.running:
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.loop_principal, daemon=True)
            self.thread.start()
            self.running = True

    def stop(self):
        if self.running:
            self.stop_event.set()
            self.running = False

# ================= FRONTEND (INTERFACE GRÁFICA) =================
class AppInterface:
    def __init__(self, root):
        self.root = root
        self.root.title("OBS Auto Recorder - Pro Manager V3.1")
        self.root.geometry("800x600")
        
        self.config_handler = ConfigHandler()
        self.backend = AutomacaoBackend(self.config_handler, self.adicionar_log)

        # Estilos manuais
        style = ttk.Style()
        style.configure("Bold.TLabel", font=("Arial", 10, "bold"))
        style.configure("Danger.TButton", foreground="red", font=("Arial", 10, "bold"))
        style.configure("Success.TButton", foreground="green", font=("Arial", 10, "bold"))
        style.configure("Action.TButton", foreground="blue", font=("Arial", 9, "bold"))
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_dash = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dash, text="Dashboard")
        self.setup_dashboard()
        
        self.tab_jogos = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_jogos, text="Meus Jogos")
        self.setup_lista_jogos()
        
        self.tab_add = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_add, text="Adicionar Manualmente")
        self.setup_adicionar()
        
        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="Configurações")
        self.setup_config()

        self.carregar_tabela_jogos()

    def adicionar_log(self, msg):
        # Thread-safe GUI update
        self.root.after(0, lambda: self._update_log_ui(msg))

    def _update_log_ui(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def toggle_servico(self):
        if not self.backend.running:
            self.backend.start()
            self.btn_status.config(text="PARAR SERVIÇO", style="Danger.TButton") 
            self.lbl_status.config(text="Status: RODANDO", foreground="green")
        else:
            self.backend.stop()
            self.btn_status.config(text="INICIAR SERVIÇO", style="Success.TButton")
            self.lbl_status.config(text="Status: PARADO", foreground="red")

    def executar_varredura_thread(self):
        self.btn_scan.config(state="disabled", text="Rastreando...")
        self.adicionar_log("--- Iniciando busca automática de jogos... ---")
        
        def worker():
            qtd = self.backend.realizar_varredura_completa()
            self.root.after(0, lambda: self.finalizar_varredura_ui(qtd))
            
        threading.Thread(target=worker, daemon=True).start()

    def finalizar_varredura_ui(self, qtd_novos):
        self.btn_scan.config(state="normal", text="🔍 Rastrear Jogos Automaticamente")
        self.carregar_tabela_jogos()
        messagebox.showinfo("Concluído", f"Varredura finalizada!\n{qtd_novos} novos jogos adicionados.")

    def setup_dashboard(self):
        frame = ttk.Frame(self.tab_dash, padding=20)
        frame.pack(fill="both", expand=True)
        panel = ttk.LabelFrame(frame, text="Controle do Robô", padding=15)
        panel.pack(fill="x", pady=(0, 20))
        self.lbl_status = ttk.Label(panel, text="Status: PARADO", font=("Arial", 14, "bold"), foreground="red")
        self.lbl_status.pack(side="left", padx=20)
        self.btn_status = ttk.Button(panel, text="INICIAR SERVIÇO", command=self.toggle_servico, style="Success.TButton")
        self.btn_status.pack(side="right", padx=20, ipadx=20, ipady=5)
        lbl_log = ttk.Label(frame, text="Logs de Atividade:", font=("Arial", 10, "bold"))
        lbl_log.pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(frame, height=15, state='disabled', font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, pady=5)

    def setup_lista_jogos(self):
        frame = ttk.Frame(self.tab_jogos)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        f_top = ttk.Frame(frame)
        f_top.pack(fill="x", pady=5)
        
        ttk.Label(f_top, text="Buscar:").pack(side="left")
        self.ent_busca = ttk.Entry(f_top)
        self.ent_busca.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_busca.bind("<KeyRelease>", self.filtrar_jogos)
        
        self.btn_scan = ttk.Button(f_top, text="🔍 Rastrear Jogos Automaticamente", command=self.executar_varredura_thread, style="Action.TButton")
        self.btn_scan.pack(side="right", padx=5)
        ttk.Button(f_top, text="↻ Atualizar", command=self.carregar_tabela_jogos).pack(side="right")

        cols = ("Nome", "Origem", "Executável", "Mic")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.tree.heading("Nome", text="Nome"); self.tree.column("Nome", width=250)
        self.tree.heading("Origem", text="Plataforma"); self.tree.column("Origem", width=80, anchor="center")
        self.tree.heading("Executável", text="Executável"); self.tree.column("Executável", width=150)
        self.tree.heading("Mic", text="Mic"); self.tree.column("Mic", width=60, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.alternar_mic_ui)
        
        f_bot = ttk.Frame(frame)
        f_bot.pack(fill="x", pady=5)
        ttk.Label(f_bot, text="Duplo clique para alternar Mic", font=("Arial", 8, "italic")).pack(side="left")
        ttk.Button(f_bot, text="Excluir Jogo Selecionado", command=self.excluir_jogo).pack(side="right")

    def setup_adicionar(self):
        frame = ttk.Frame(self.tab_add, padding=30)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Nome do Jogo:").pack(anchor="w")
        self.ent_add_nome = ttk.Entry(frame); self.ent_add_nome.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text="Executável:").pack(anchor="w")
        f_exe = ttk.Frame(frame); f_exe.pack(fill="x", pady=(0, 10))
        self.ent_add_exe = ttk.Entry(f_exe); self.ent_add_exe.pack(side="left", fill="x", expand=True)
        ttk.Button(f_exe, text="Buscar", command=lambda: self.buscar_arquivo(self.ent_add_exe)).pack(side="right")
        self.var_mic_add = tk.IntVar()
        ttk.Checkbutton(frame, text="Gravar Microfone?", variable=self.var_mic_add).pack(anchor="w", pady=10)
        ttk.Button(frame, text="CADASTRAR JOGO", command=self.cadastrar_manual).pack(fill="x", ipady=10)

    def setup_config(self):
        frame = ttk.Frame(self.tab_config, padding=20)
        frame.pack(fill="both", expand=True)
        cfg = self.config_handler.config
        ttk.Label(frame, text="Caminho do executável do OBS (obs64.exe):", style="Bold.TLabel").pack(anchor="w")
        f1 = ttk.Frame(frame); f1.pack(fill="x", pady=(0, 15))
        self.ent_obs_path = ttk.Entry(f1); self.ent_obs_path.pack(side="left", fill="x", expand=True)
        self.ent_obs_path.insert(0, cfg["obs_path"])
        ttk.Button(f1, text="...", command=lambda: self.buscar_arquivo(self.ent_obs_path)).pack(side="right")
        ttk.Label(frame, text="Pasta onde salvar os vídeos:", style="Bold.TLabel").pack(anchor="w")
        f2 = ttk.Frame(frame); f2.pack(fill="x", pady=(0, 15))
        self.ent_out_dir = ttk.Entry(f2); self.ent_out_dir.pack(side="left", fill="x", expand=True)
        self.ent_out_dir.insert(0, cfg["output_dir"])
        ttk.Button(f2, text="...", command=lambda: self.buscar_pasta(self.ent_out_dir)).pack(side="right")
        ttk.Label(frame, text="OBS WebSocket Senha:", style="Bold.TLabel").pack(anchor="w")
        self.ent_ws_pass = ttk.Entry(frame, show="*")
        self.ent_ws_pass.pack(fill="x", pady=(0, 15))
        self.ent_ws_pass.insert(0, cfg["obs_ws_password"])
        ttk.Button(frame, text="SALVAR CONFIGURAÇÕES", command=self.salvar_configs).pack(pady=20, ipadx=20, ipady=5)

    def buscar_arquivo(self, entry_widget):
        f = filedialog.askopenfilename(filetypes=[("Executáveis", "*.exe")])
        if f:
            entry_widget.delete(0, tk.END); entry_widget.insert(0, f)
            if entry_widget == self.ent_add_exe and not self.ent_add_nome.get():
                self.ent_add_nome.insert(0, os.path.basename(f).replace(".exe", "").title())

    def buscar_pasta(self, entry_widget):
        d = filedialog.askdirectory()
        if d: entry_widget.delete(0, tk.END); entry_widget.insert(0, d)

    def salvar_configs(self):
        new_cfg = self.config_handler.config.copy()
        new_cfg["obs_path"] = self.ent_obs_path.get()
        new_cfg["obs_dir"] = os.path.dirname(self.ent_obs_path.get())
        new_cfg["output_dir"] = self.ent_out_dir.get()
        new_cfg["obs_ws_password"] = self.ent_ws_pass.get()
        self.config_handler.save_config(new_cfg)
        messagebox.showinfo("Sucesso", "Configurações salvas!")

    def carregar_tabela_jogos(self):
        self.tree.delete(*self.tree.get_children())
        self.jogos_cache = []
        conn = self.backend.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT nome, origem, executavel, usar_mic, appid FROM jogos ORDER BY nome ASC")
        for row in cursor.fetchall():
            self.jogos_cache.append(row)
            self.inserir_linha_tree(row)
        conn.close()

    def inserir_linha_tree(self, row):
        mic_str = "ON" if row[3] else "OFF"
        tag = "on" if row[3] else "off"
        self.tree.insert("", "end", values=(row[0], row[1], row[2], mic_str), tags=(tag,))
        self.tree.tag_configure("on", foreground="green", font=("Arial", 9, "bold"))
        self.tree.tag_configure("off", foreground="gray")

    def alternar_mic_ui(self, event):
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0])
        nome_jogo = item['values'][0]
        conn = self.backend.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT usar_mic, appid FROM jogos WHERE nome = ?", (nome_jogo,))
        data = cursor.fetchone()
        if data:
            novo_status = 0 if data[0] == 1 else 1
            cursor.execute("UPDATE jogos SET usar_mic = ? WHERE appid = ?", (novo_status, data[1]))
            conn.commit()
        conn.close()
        self.carregar_tabela_jogos()

    def excluir_jogo(self):
        sel = self.tree.selection()
        if sel:
            nome = self.tree.item(sel[0])['values'][0]
            if messagebox.askyesno("Excluir", f"Remover {nome}?"):
                conn = self.backend.conectar_db()
                conn.execute("DELETE FROM jogos WHERE nome = ?", (nome,))
                conn.commit()
                conn.close()
                self.carregar_tabela_jogos()

    def cadastrar_manual(self):
        nome = self.ent_add_nome.get()
        exe = os.path.basename(self.ent_add_exe.get())
        path_dir = os.path.dirname(self.ent_add_exe.get())
        mic = self.var_mic_add.get()
        if nome and exe:
            conn = self.backend.conectar_db()
            try:
                conn.execute("INSERT INTO jogos (appid, nome, executavel, diretorio_instalacao, usar_mic, origem) VALUES (?, ?, ?, ?, ?, 'Manual')",
                             (str(uuid.uuid4()), nome, exe, path_dir, mic))
                conn.commit()
                messagebox.showinfo("Sucesso", "Jogo cadastrado!")
                self.ent_add_nome.delete(0, tk.END)
                self.ent_add_exe.delete(0, tk.END)
                self.carregar_tabela_jogos()
            except Exception as e:
                messagebox.showerror("Erro", str(e))
            finally:
                conn.close()

    def filtrar_jogos(self, event):
        termo = self.ent_busca.get().lower()
        self.tree.delete(*self.tree.get_children())
        for row in self.jogos_cache:
            if termo in row[0].lower() or termo in row[2].lower():
                self.inserir_linha_tree(row)

if __name__ == "__main__":
    root = tk.Tk()
    app = AppInterface(root)

    root.mainloop()
