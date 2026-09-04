import streamlit as st
import pandas as pd
import json
import os
import gspread
from google.oauth2.service_account import Credentials

# ==============================================================================
# CONFIGURAÇÃO DE PÁGINA E ESTILOS
# ==============================================================================
st.set_page_config(
    page_title="Central Unificada de Planilhas",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        html, body, [data-testid="stAppViewContainer"] { overflow: hidden; }
        .block-container { padding-top: 0.3rem !important; padding-bottom: 0rem !important; padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        div[data-testid="column"] { padding: 0px 4px !important; }
        .stButton>button { width: 100%; margin-top: 24px; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# PERSISTÊNCIA LOCAL (USUÁRIOS E MAPA DE PLANILHAS)
# ==============================================================================
ARQUIVO_DADOS = "dados_sistema.json"

DADOS_INICIAIS = {
    "usuarios": {
        "admin": {
            "senha": "123",
            "nome": "Gerência / Admin",
            "setores": ["Visão Geral", "Almoxarifado", "Containers", "Painel Admin"],
            "e_admin": True
        },
        "almoxarife": {
            "senha": "456",
            "nome": "Operador de Almoxarifado",
            "setores": ["Almoxarifado"],
            "e_admin": False
        }
    },
    "planilhas": {
        "Almoxarifado": {
            "Controle": "1nb-gVt6e98Kh4BAYl9l-dgspleRHZDfe8DAT2B1OB_I",
            "Ferro Quantidade": "1kyrYqJoJLyaL8fvCFVvnFgAbEHIAv6h1W2ZHt1Hmhn4"
        },
        "Containers": {
            "Controle de containers em patio": "1Im_QMBgD1GYDSe6v4-xvN6rOHUAGTZjA-fl3hB1w5tg"
        }
    }
}

def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        salvar_dados(DADOS_INICIAIS)
        return DADOS_INICIAIS
    with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_dados(dados):
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

dados_sistema = carregar_dados()
USUARIOS = dados_sistema["usuarios"]
PLANILHAS_POR_SETOR = dados_sistema["planilhas"]

# ==============================================================================
# CONEXÃO API GOOGLE SHEETS VIA GSPREAD (COM CACHE E DIAGNÓSTICO)
# ==============================================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def conectar_google_api():
    """Autentica com o Google Drive/Sheets usando a Service Account."""
    try:
        # Prioridade 1: Arquivo chave.json local (Desenvolvimento)
        if os.path.exists("chave.json"):
            creds = Credentials.from_service_account_file("chave.json", scopes=SCOPES)
            return gspread.authorize(creds)
        
        # Prioridade 2: Secrets do Streamlit Cloud (Produção)
        elif "gcp_service_account" in st.secrets:
            credentials_info = dict(st.secrets["gcp_service_account"])
            
            if "private_key" in credentials_info:
                credentials_info["private_key"] = credentials_info["private_key"].replace("\\n", "\n")
                
            creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
            return gspread.authorize(creds)
            
        else:
            st.error("⚠️ Nenhuma fonte de credencial encontrada (`chave.json` ou `st.secrets`).")
            return None

    except Exception as e:
        st.error(f"⚠️ Erro ao tentar autenticar na API do Google: {e}")
        return None

client_gspread = conectar_google_api()

@st.cache_data(ttl=180)  # Mantém os dados em cache por 3 minutos para evitar chamadas redundantes
def ler_planilha_api(spreadsheet_id):
    """Lê os dados da primeira aba da planilha usando a Service Account."""
    if not client_gspread:
        return None
    try:
        sheet = client_gspread.open_by_key(spreadsheet_id).sheet1
        dados = sheet.get_all_records()
        return pd.DataFrame(dados)
    except Exception as e:
        st.error(f"Erro ao acessar planilha via API: {e}")
        return None

def salvar_alteracoes_api(spreadsheet_id, df_atualizado):
    """Atualiza os dados da planilha no Google Sheets."""
    if not client_gspread:
        return False
    try:
        sheet = client_gspread.open_by_key(spreadsheet_id).sheet1
        sheet.clear()
        sheet.update([df_atualizado.columns.values.tolist()] + df_atualizado.values.tolist())
        st.cache_data.clear()  # Invalida o cache local para refletir a edição na hora
        return True
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")
        return False

# ==============================================================================
# CONTROLE DE SESSÃO / LOGIN
# ==============================================================================
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None

if st.session_state["usuario_logado"] is None:
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, col_login, c2 = st.columns([1, 1.2, 1])
    
    with col_login:
        st.title("🔒 Acesso ao Sistema")
        st.caption("Digite suas credenciais para acessar as planilhas do seu setor.")
        
        with st.form("form_login"):
            usuario = st.text_input("Usuário").strip().lower()
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button("Entrar no Sistema")
            
            if btn_entrar:
                if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
                    st.session_state["usuario_logado"] = usuario
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

else:
    dados_usuario = USUARIOS[st.session_state["usuario_logado"]]
    setores_permitidos = dados_usuario["setores"]
    
    c_setor, c_planilha, c_botao, c_user = st.columns([1.2, 1.5, 1.2, 1])
    
    with c_setor:
        setor_selecionado = st.selectbox("🏢 Setor:", setores_permitidos)
        
    # --- VISÃO GERAL ---
    if setor_selecionado == "Visão Geral":
        with c_planilha:
            st.selectbox("📁 Planilha:", ["Painel Consolidado"], disabled=True)
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout_dash"):
                st.session_state["usuario_logado"] = None
                st.rerun()
                
        st.markdown("---")
        st.subheader("📊 Visão Geral / Dashboard Central")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ferramentas Emprestadas", "18", delta="+2 hoje")
        m2.metric("Itens em Manutenção", "4", delta="-1 semana")
        m3.metric("Containers no Pátio", "12", delta="0")
        m4.metric("Conferências Pendentes", "3", delta="-5", delta_color="inverse")

    # --- PAINEL ADMIN ---
    elif setor_selecionado == "Painel Admin":
        with c_planilha:
            st.selectbox("📁 Planilha:", ["Gestão do Sistema"], disabled=True)
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout_admin"):
                st.session_state["usuario_logado"] = None
                st.rerun()

        st.markdown("---")
        st.subheader("⚙️ Painel do Administrador")

        tab_planilhas, tab_cadastrar_usr, tab_gerenciar_usr = st.tabs([
            "➕ Cadastrar Planilha", 
            "👤 Cadastrar Usuário", 
            "📋 Gerenciar / Deletar Usuários"
        ])

        with tab_planilhas:
            st.markdown("### Cadastrar Nova Planilha")
            setores_existentes = list(PLANILHAS_POR_SETOR.keys())
            novo_setor_check = st.checkbox("Criar um novo setor")
            setor_dest = st.text_input("Nome do Novo Setor").strip() if novo_setor_check else st.selectbox("Selecionar Setor Existente", setores_existentes)
            nome_planilha = st.text_input("Nome da Planilha").strip()
            id_planilha_input = st.text_input("ID do Google Sheets").strip()

            if st.button("Salvar Planilha"):
                if setor_dest and nome_planilha and id_planilha_input:
                    if setor_dest not in PLANILHAS_POR_SETOR:
                        PLANILHAS_POR_SETOR[setor_dest] = {}
                    PLANILHAS_POR_SETOR[setor_dest][nome_planilha] = id_planilha_input
                    dados_sistema["planilhas"] = PLANILHAS_POR_SETOR
                    salvar_dados(dados_sistema)
                    st.success(f"Planilha '{nome_planilha}' adicionada!")
                    st.rerun()

        with tab_cadastrar_usr:
            st.markdown("### Cadastrar Novo Usuário")
            novo_login = st.text_input("Login (ex: joao)").strip().lower()
            nova_senha = st.text_input("Senha Inicial").strip()
            nome_completo = st.text_input("Nome Exibido").strip()
            todos_setores = ["Visão Geral"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]
            setores_usuario = st.multiselect("Setores Permitidos", todos_setores)
            e_admin_check = st.checkbox("Tornar Administrador")

            if st.button("Salvar Usuário"):
                if novo_login and nova_senha and nome_completo and setores_usuario:
                    USUARIOS[novo_login] = {
                        "senha": nova_senha,
                        "nome": nome_completo,
                        "setores": setores_usuario,
                        "e_admin": e_admin_check
                    }
                    dados_sistema["usuarios"] = USUARIOS
                    salvar_dados(dados_sistema)
                    st.success(f"Usuário '{novo_login}' cadastrado!")
                    st.rerun()

        with tab_gerenciar_usr:
            st.markdown("### Usuários Cadastrados")
            for login, info in list(USUARIOS.items()):
                c_login, c_nome, c_set, c_act = st.columns([1, 1.5, 2, 1])
                c_login.write(f"`{login}`")
                c_nome.write(info["nome"])
                c_set.write(", ".join(info["setores"]))
                if login == st.session_state["usuario_logado"]:
                    c_act.caption("*(Você)*")
                else:
                    if c_act.button("🗑️ Deletar", key=f"btn_del_{login}"):
                        del USUARIOS[login]
                        dados_sistema["usuarios"] = USUARIOS
                        salvar_dados(dados_sistema)
                        st.rerun()

    # --- OPERAÇÃO DE PLANILHAS (VISUALIZAÇÃO E EDIÇÃO RÁPIDA) ---
    else:
        planilhas_do_setor = PLANILHAS_POR_SETOR.get(setor_selecionado, {})
        
        with c_planilha:
            if planilhas_do_setor:
                planilha_selecionada = st.selectbox("📁 Planilha:", list(planilhas_do_setor.keys()))
                id_planilha = planilhas_do_setor[planilha_selecionada]
                url_google_sheets = f"https://docs.google.com/spreadsheets/d/{id_planilha}/edit"
            else:
                st.selectbox("📁 Planilha:", ["Nenhuma planilha cadastrada"], disabled=True)
                id_planilha = None
                url_google_sheets = "#"
            
        with c_botao:
            if url_google_sheets != "#":
                st.markdown(
                    f'<a href="{url_google_sheets}" target="_blank">'
                    f'<button style="width:100%; height:38px; margin-top:24px; background-color:#2e7d32; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">'
                    f'🔗 Abrir no Google Sheets</button></a>',
                    unsafe_allow_html=True
                )
            
        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout"):
                st.session_state["usuario_logado"] = None
                st.rerun()

        if id_planilha:
            df_dados = ler_planilha_api(id_planilha)
            if df_dados is not None:
                st.caption("⚡ **Modo Nativo via API**: Você pode editar os valores na tabela abaixo e salvar direto no Google Sheets.")
                
                # Editor de dados nativo do Streamlit
                df_editado = st.data_editor(df_dados, use_container_width=True, height=550, num_rows="dynamic")
                
                col_salvar, col_vazio = st.columns([1, 3])
                with col_salvar:
                    if st.button("💾 Salvar Alterações na Nuvem"):
                        if salvar_alteracoes_api(id_planilha, df_editado):
                            st.success("Planilha sincronizada com sucesso!")
                            st.rerun()
            else:
                st.warning("Não foi possível carregar a planilha. Verifique se compartilhou a planilha como Editor com o e-mail da Service Account.")
        else:
            st.info("Nenhuma planilha vinculada a este setor.")
