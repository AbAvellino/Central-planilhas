import streamlit as st
import pandas as pd
import json
import os
import hashlib
from datetime import datetime
import io
import gspread
from google.oauth2.service_account import Credentials

# ==============================================================================
# CONFIGURAÇÃO DE PÁGINA E ESTILOS CSS
# ==============================================================================
st.set_page_config(
    page_title="Central Unificada de Planilhas",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container { 
            padding-top: 1rem !important; 
            padding-bottom: 1rem !important; 
            padding-left: 1.5rem !important; 
            padding-right: 1.5rem !important; 
        }
        #MainMenu, footer, header { visibility: hidden; }
        .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; }
        .log-box { font-family: monospace; font-size: 12px; background-color: #1e1e2f; padding: 10px; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# CONFIGURAÇÃO DA PLANILHA DE BANCO DE DADOS CENTRAL
# ==============================================================================
# ⚠️ COLE AQUI O ID DA PLANILHA 'Central_Configuracoes_Sistema' QUE VOCÊ CRIOU
ID_PLANILHA_SISTEMA = "1s9t8pwhlc2Kg2hNJNPTHi7bTjMm9ZyRQhwSPacJYN2k"

# ==============================================================================
# FUNÇÕES DE CRIPTOGRAFIA DE SENHA
# ==============================================================================
def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def verificar_senha(senha_input: str, senha_hash: str) -> bool:
    return hash_senha(senha_input) == senha_hash

# ==============================================================================
# CONEXÃO API GOOGLE SHEETS
# ==============================================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def conectar_google_api():
    try:
        if "gcp_service_account" in st.secrets:
            credentials_info = dict(st.secrets["gcp_service_account"])
            if "private_key" in credentials_info:
                credentials_info["private_key"] = credentials_info["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
            return gspread.authorize(creds)
        elif os.path.exists("chave.json"):
            creds = Credentials.from_service_account_file("chave.json", scopes=SCOPES)
            return gspread.authorize(creds)
        return None
    except Exception as e:
        st.error(f"⚠️ Erro ao conectar na API: {e}")
        return None

client_gspread = conectar_google_api()

# ==============================================================================
# PERSISTÊNCIA NO GOOGLE SHEETS (DADOS, USUÁRIOS E LOGS)
# ==============================================================================
def inicializar_planilha_sistema():
    """Garante que a planilha central do sistema exista e tenha os dados padrão."""
    if not client_gspread or ID_PLANILHA_SISTEMA == "COLE_AQUI_O_ID_DA_SUA_PLANILHA_SISTEMA":
        return
    
    try:
        sh = client_gspread.open_by_key(ID_PLANILHA_SISTEMA)
        
        # 1. Verificar/Inicializar Usuários
        try:
            ws_usr = sh.worksheet("Usuarios")
            if not ws_usr.get_all_values():
                raise Exception("Aba vazia")
        except:
            ws_usr = sh.worksheet("Usuarios") if "Usuarios" in [w.title for w in sh.worksheets()] else sh.add_worksheet("Usuarios", 100, 10)
            ws_usr.clear()
            ws_usr.append_row(["login", "senha", "nome", "setores", "permissao", "e_admin"])
            ws_usr.append_rows([
                ["admin", hash_senha("123"), "Gerência / Admin", "Visão Geral,Busca Global,Almoxarifado,Containers,Painel Admin", "Escrita", "True"],
                ["almoxarife", hash_senha("456"), "Operador de Almoxarifado", "Visão Geral,Almoxarifado", "Escrita", "False"]
            ])

        # 2. Verificar/Inicializar Planilhas
        try:
            ws_plan = sh.worksheet("Planilhas")
            if not ws_plan.get_all_values():
                raise Exception("Aba vazia")
        except:
            ws_plan = sh.worksheet("Planilhas") if "Planilhas" in [w.title for w in sh.worksheets()] else sh.add_worksheet("Planilhas", 100, 10)
            ws_plan.clear()
            ws_plan.append_row(["setor", "nome_planilha", "spreadsheet_id"])
            ws_plan.append_rows([
                ["Almoxarifado", "Controle", "1nb-gVt6e98Kh4BAYl9l-dgspleRHZDfe8DAT2B1OB_I"],
                ["Almoxarifado", "Ferro Quantidade", "1kyrYqJoJLyaL8fvCFVvnFgAbEHIAv6h1W2ZHt1Hmhn4"],
                ["Containers", "Controle de containers em patio", "1Im_QMBgD1GYDSe6v4-xvN6rOHUAGTZjA-fl3hB1w5tg"]
            ])

        # 3. Verificar/Inicializar Logs
        try:
            sh.worksheet("Logs")
        except:
            ws_log = sh.add_worksheet("Logs", 500, 10)
            ws_log.append_row(["data_hora", "usuario", "acao", "detalhe"])
            
    except Exception as e:
        st.error(f"Erro ao inicializar planilha do sistema: {e}")

inicializar_planilha_sistema()

@st.cache_data(ttl=30)
def carregar_dados():
    """Carrega os usuários e planilhas diretamente do Google Sheets."""
    if not client_gspread or ID_PLANILHA_SISTEMA == "COLE_AQUI_O_ID_DA_SUA_PLANILHA_SISTEMA":
        st.warning("⚠️ Insira o ID_PLANILHA_SISTEMA válido no código para habilitar a gravação permanente.")
        return {"usuarios": {}, "planilhas": {}}

    try:
        sh = client_gspread.open_by_key(ID_PLANILHA_SISTEMA)
        
        # Carregar Usuários
        df_usr = pd.DataFrame(sh.worksheet("Usuarios").get_all_records())
        usuarios = {}
        if not df_usr.empty:
            for _, r in df_usr.iterrows():
                usuarios[str(r['login']).strip().lower()] = {
                    "senha": str(r['senha']),
                    "nome": str(r['nome']),
                    "setores": [s.strip() for s in str(r['setores']).split(',') if s.strip()],
                    "permissao": str(r['permissao']),
                    "e_admin": str(r['e_admin']).lower() == 'true'
                }

        # Carregar Planilhas
        df_plan = pd.DataFrame(sh.worksheet("Planilhas").get_all_records())
        planilhas = {}
        if not df_plan.empty:
            for _, r in df_plan.iterrows():
                setor = str(r['setor']).strip()
                nome = str(r['nome_planilha']).strip()
                sp_id = str(r['spreadsheet_id']).strip()
                
                if setor not in planilhas:
                    planilhas[setor] = {}
                planilhas[setor][nome] = sp_id

        return {"usuarios": usuarios, "planilhas": planilhas}
    except Exception as e:
        st.error(f"Erro ao carregar dados do sistema no Google Sheets: {e}")
        return {"usuarios": {}, "planilhas": {}}

def salvar_usuarios_sheets(usuarios_dict):
    """Atualiza toda a aba de usuários na planilha do Google Sheets."""
    if not client_gspread: return
    try:
        sh = client_gspread.open_by_key(ID_PLANILHA_SISTEMA)
        ws = sh.worksheet("Usuarios")
        ws.clear()
        
        rows = [["login", "senha", "nome", "setores", "permissao", "e_admin"]]
        for login, info in usuarios_dict.items():
            setores_str = ",".join(info["setores"])
            rows.append([
                login,
                info["senha"],
                info["nome"],
                setores_str,
                info["permissao"],
                str(info["e_admin"])
            ])
        ws.update(rows)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar usuários: {e}")

def salvar_planilhas_sheets(planilhas_dict):
    """Atualiza a aba de planilhas cadastradas no Google Sheets."""
    if not client_gspread: return
    try:
        sh = client_gspread.open_by_key(ID_PLANILHA_SISTEMA)
        ws = sh.worksheet("Planilhas")
        ws.clear()
        
        rows = [["setor", "nome_planilha", "spreadsheet_id"]]
        for setor, p_map in planilhas_dict.items():
            for nome, sp_id in p_map.items():
                rows.append([setor, nome, sp_id])
        ws.update(rows)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar planilhas: {e}")

def registrar_log(usuario, acao, detalhe):
    """Grava o log de auditoria no Google Sheets."""
    if not client_gspread or ID_PLANILHA_SISTEMA == "COLE_AQUI_O_ID_DA_SUA_PLANILHA_SISTEMA": return
    try:
        sh = client_gspread.open_by_key(ID_PLANILHA_SISTEMA)
        ws = sh.worksheet("Logs")
        ws.insert_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            usuario,
            acao,
            detalhe
        ], index=2) # Insere logo abaixo do cabeçalho
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

dados_sistema = carregar_dados()
USUARIOS = dados_sistema["usuarios"]
PLANILHAS_POR_SETOR = dados_sistema["planilhas"]

# ==============================================================================
# FUNÇÕES DE LEITURA E ESCRITA DAS PLANILHAS OPERACIONAIS
# ==============================================================================
@st.cache_data(ttl=120)
def obter_abas_planilha(spreadsheet_id):
    if not client_gspread: return []
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        return [ws.title for ws in sh.worksheets()]
    except Exception:
        return []

@st.cache_data(ttl=120)
def ler_planilha_api(spreadsheet_id, nome_aba=None):
    if not client_gspread: return None
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        sheet = sh.worksheet(nome_aba) if nome_aba else sh.sheet1
        dados = sheet.get_all_records()
        return pd.DataFrame(dados)
    except Exception as e:
        st.error(f"Erro ao acessar planilha/aba via API: {e}")
        return None

def salvar_alteracoes_api(spreadsheet_id, df_atualizado, nome_aba=None):
    if not client_gspread: return False
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        sheet = sh.worksheet(nome_aba) if nome_aba else sh.sheet1
        sheet.clear()
        sheet.update([df_atualizado.columns.values.tolist()] + df_atualizado.values.tolist())
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")
        return False

# ==============================================================================
# CONTROLE DE SESSÃO E LOGIN
# ==============================================================================
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None

if st.session_state["usuario_logado"] is None:
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, col_login, c2 = st.columns([1, 1.2, 1])
    
    with col_login:
        st.title("🔒 Central Unificada")
        st.caption("Acesse com suas credenciais seguras.")
        
        with st.form("form_login"):
            usuario = st.text_input("👤 Usuário").strip().lower()
            senha = st.text_input("🔑 Senha", type="password")
            btn_entrar = st.form_submit_button("🚀 Entrar no Sistema")
            
            if btn_entrar:
                if usuario in USUARIOS:
                    senha_armazenada = USUARIOS[usuario]["senha"]
                    senha_valida = verificar_senha(senha, senha_armazenada) or (senha == senha_armazenada)
                    
                    if senha_valida:
                        if senha == senha_armazenada:
                            USUARIOS[usuario]["senha"] = hash_senha(senha)
                            salvar_usuarios_sheets(USUARIOS)

                        st.session_state["usuario_logado"] = usuario
                        registrar_log(usuario, "Login", "Usuário autenticado com sucesso")
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
                else:
                    st.error("Usuário não encontrado.")

else:
    dados_usuario = USUARIOS[st.session_state["usuario_logado"]]
    setores_permitidos = dados_usuario["setores"]
    
    # BARRA FIXA SUPERIOR DE SELEÇÃO
    c_setor, c_planilha, c_modo, c_user = st.columns([1.2, 1.3, 1.5, 0.8])
    
    with c_setor:
        setor_selecionado = st.selectbox("🏢 Setor / Área", setores_permitidos)
        
    # --- VISÃO GERAL ---
    if setor_selecionado == "Visão Geral":
        with c_planilha:
            st.selectbox("📁 Planilha", ["Painel Consolidado"], disabled=True)
        with c_modo:
            st.empty()
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout_dash"):
                st.session_state["usuario_logado"] = None
                st.rerun()
                
        st.markdown("---")
        st.subheader("📊 Visão Geral / Dashboard Central")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🛠️ Ferramentas Emprestadas", "18", delta="+2 hoje")
        m2.metric("🔧 Itens em Manutenção", "4", delta="-1 semana")
        m3.metric("📦 Containers no Pátio", "12", delta="0")
        m4.metric("📋 Conferências Pendentes", "3", delta="-5", delta_color="inverse")

    # --- BUSCA GLOBAL EM TODAS AS PLANILHAS ---
    elif setor_selecionado == "Busca Global":
        with c_planilha:
            st.selectbox("📁 Planilha", ["Varredura Multisetor"], disabled=True)
        with c_modo:
            st.empty()
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout_search"):
                st.session_state["usuario_logado"] = None
                st.rerun()

        st.markdown("---")
        st.subheader("🔍 Busca Global em Todas as Planilhas")
        termo_busca = st.text_input("Digite o código, nome de item, ID de container ou palavra-chave:")
        
        if st.button("🔎 Pesquisar no Sistema") and termo_busca:
            encontrados = 0
            with st.spinner("Pesquisando em todas as planilhas cadastradas..."):
                for setor, planilhas in PLANILHAS_POR_SETOR.items():
                    for nome_plan, sheet_id in planilhas.items():
                        df = ler_planilha_api(sheet_id)
                        if df is not None and not df.empty:
                            mascara = df.astype(str).apply(lambda row: row.str.contains(termo_busca, case=False, na=False)).any(axis=1)
                            resultados = df[mascara]
                            if not resultados.empty:
                                encontrados += len(resultados)
                                st.write(f"📍 **Setor:** `{setor}` | **Planilha:** `{nome_plan}` ({len(resultados)} registro(s) encontrado(s))")
                                st.dataframe(resultados, use_container_width=True)
            if encontrados == 0:
                st.warning("Nenhum resultado encontrado para o termo pesquisado.")

    # --- PAINEL ADMIN E LOGS ---
    elif setor_selecionado == "Painel Admin":
        with c_planilha:
            st.selectbox("📁 Planilha", ["Gestão do Sistema"], disabled=True)
        with c_modo:
            st.empty()
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout_admin"):
                st.session_state["usuario_logado"] = None
                st.rerun()

        st.markdown("---")
        st.subheader("⚙️ Painel do Administrador & Logs de Auditoria")

        tab_planilhas, tab_cadastrar_usr, tab_gerenciar_usr, tab_logs = st.tabs([
            "➕ Cadastrar Planilha", 
            "👤 Cadastrar Novo Usuário", 
            "📋 Gerenciar / Alterar / Excluir Usuários",
            "📜 Logs de Auditoria"
        ])

        with tab_planilhas:
            st.markdown("### Cadastrar Nova Planilha")
            setores_existentes = list(PLANILHAS_POR_SETOR.keys())
            novo_setor_check = st.checkbox("Criar um novo setor")
            setor_dest = st.text_input("Nome do Novo Setor").strip() if novo_setor_check else st.selectbox("Selecionar Setor Existente", setores_existentes)
            nome_planilha = st.text_input("Nome da Planilha").strip()
            id_planilha_input = st.text_input("ID do Google Sheets").strip()

            if st.button("💾 Salvar Planilha"):
                if setor_dest and nome_planilha and id_planilha_input:
                    if setor_dest not in PLANILHAS_POR_SETOR:
                        PLANILHAS_POR_SETOR[setor_dest] = {}
                    PLANILHAS_POR_SETOR[setor_dest][nome_planilha] = id_planilha_input
                    
                    salvar_planilhas_sheets(PLANILHAS_POR_SETOR)
                    registrar_log(st.session_state["usuario_logado"], "Cadastro Planilha", f"Planilha '{nome_planilha}' no setor '{setor_dest}'")
                    st.success("Planilha salva com sucesso no Google Sheets!")
                    st.rerun()

        with tab_cadastrar_usr:
            st.markdown("### Cadastrar Novo Usuário com Criptografia")
            novo_login = st.text_input("Login (ex: joao)").strip().lower()
            nova_senha = st.text_input("Senha Inicial", type="password").strip()
            nome_completo = st.text_input("Nome Exibido").strip()
            
            todos_setores = ["Visão Geral", "Busca Global"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]
            setores_usuario = st.multiselect("Setores Permitidos:", todos_setores, default=["Visão Geral", "Busca Global"])
            permissao_tipo = st.radio("Nível de Acesso às Planilhas:", ["Escrita", "Leitura"], horizontal=True)
            e_admin_check = st.checkbox("Tornar Administrador do Sistema")

            if st.button("👤 Salvar Usuário"):
                if novo_login and nova_senha and nome_completo and setores_usuario:
                    USUARIOS[novo_login] = {
                        "senha": hash_senha(nova_senha),
                        "nome": nome_completo,
                        "setores": setores_usuario,
                        "permissao": permissao_tipo,
                        "e_admin": e_admin_check
                    }
                    salvar_usuarios_sheets(USUARIOS)
                    registrar_log(st.session_state["usuario_logado"], "Cadastro Usuário", f"Usuário '{novo_login}' criado.")
                    st.success(f"Usuário '{novo_login}' cadastrado permanentemente!")
                    st.rerun()

        with tab_gerenciar_usr:
            st.markdown("### Gerenciar, Alterar e Excluir Usuários")
            todos_setores = ["Visão Geral", "Busca Global"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]

            for login, info in list(USUARIOS.items()):
                with st.expander(f"👤 **{info['nome']}** (`login: {login}`)", expanded=False):
                    c_n, c_s = st.columns(2)
                    with c_n:
                        novo_nome_val = st.text_input("Nome do Usuário", value=info["nome"], key=f"nome_{login}")
                    with c_s:
                        nova_senha_val = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key=f"pwd_{login}")

                    c_perm1, c_perm2, c_admin = st.columns([2, 1, 1])
                    with c_perm1:
                        novos_setores = st.multiselect("Setores liberados:", options=todos_setores, default=info["setores"], key=f"ms_{login}")
                    with c_perm2:
                        nova_perm = st.selectbox("Modo de Acess
