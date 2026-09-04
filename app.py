import streamlit as st
import pandas as pd
import json
import os
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
        /* 1. Ocupação máxima da tela */
        .block-container { 
            padding-top: 0rem !important; 
            padding-bottom: 0rem !important; 
            padding-left: 0.5rem !important; 
            padding-right: 0.5rem !important; 
        }
        #MainMenu, footer, header { visibility: hidden; }

        /* 2. Botão Flutuante no Canto Superior Direito */
        .top-right-toggle-btn {
            position: fixed;
            top: 10px;
            right: 20px;
            z-index: 9999999;
            background-color: #0d6efd;
            color: #ffffff;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .top-right-toggle-btn:hover {
            background-color: #0b5ed7;
            transform: scale(1.05);
        }

        /* 3. Painel de Controle Flutuante */
        div[data-testid="stHorizontalBlock"]:has(div.top-bar-marker) {
            position: fixed;
            top: -160px;
            left: 2%;
            right: 2%;
            z-index: 999999;
            background: #1e1e2f;
            border: 1px solid #33334d;
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
            padding: 15px 20px;
            box-shadow: 0px 8px 24px rgba(0, 0, 0, 0.6);
            transition: top 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        /* Exibe o painel flutuante ao passar o mouse na área superior direita */
        div[data-testid="stHorizontalBlock"]:has(div.top-bar-marker):hover,
        .top-right-toggle-btn:hover + div[data-testid="stHorizontalBlock"]:has(div.top-bar-marker) {
            top: 0px !important;
        }

        /* 4. Estilização dos Botões */
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            font-weight: 600;
        }
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
# CONEXÃO API GOOGLE SHEETS VIA GSPREAD
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
            
        else:
            return None
    except Exception as e:
        st.error(f"⚠️ Erro ao tentar autenticar na API do Google: {e}")
        return None

client_gspread = conectar_google_api()

@st.cache_data(ttl=180)
def ler_planilha_api(spreadsheet_id):
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
    if not client_gspread:
        return False
    try:
        sheet = client_gspread.open_by_key(spreadsheet_id).sheet1
        sheet.clear()
        sheet.update([df_atualizado.columns.values.tolist()] + df_atualizado.values.tolist())
        st.cache_data.clear()
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
        st.title("🔒 Central Unificada")
        st.caption("Digite suas credenciais para acessar as planilhas do seu setor.")
        
        with st.form("form_login"):
            usuario = st.text_input("👤 Usuário").strip().lower()
            senha = st.text_input("🔑 Senha", type="password")
            btn_entrar = st.form_submit_button("🚀 Entrar no Sistema")
            
            if btn_entrar:
                if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
                    st.session_state["usuario_logado"] = usuario
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

else:
    dados_usuario = USUARIOS[st.session_state["usuario_logado"]]
    setores_permitidos = dados_usuario["setores"]
    
    # 1. Botão visual no canto superior direito
    st.markdown('<div class="top-right-toggle-btn">⚙️ Painel de Opções 🔽</div>', unsafe_allow_html=True)
    
    # 2. Barra Flutuante de Seleção
    c_setor, c_planilha, c_modo, c_user = st.columns([1.2, 1.3, 1.5, 0.8])
    
    with c_setor:
        st.markdown('<div class="top-bar-marker"></div>', unsafe_allow_html=True)
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
                
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.subheader("📊 Visão Geral / Dashboard Central")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🛠️ Ferramentas Emprestadas", "18", delta="+2 hoje")
        m2.metric("🔧 Itens em Manutenção", "4", delta="-1 semana")
        m3.metric("📦 Containers no Pátio", "12", delta="0")
        m4.metric("📋 Conferências Pendentes", "3", delta="-5", delta_color="inverse")

    # --- PAINEL ADMIN ---
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

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.subheader("⚙️ Painel do Administrador & Permissões")

        tab_planilhas, tab_cadastrar_usr, tab_gerenciar_usr = st.tabs([
            "➕ Cadastrar Planilha", 
            "👤 Cadastrar Novo Usuário", 
            "📋 Gerenciar / Alterar Permissões"
        ])

        with tab_planilhas:
            st.markdown("### Cadastrar Nova Planilha em um Setor")
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
                    dados_sistema["planilhas"] = PLANILHAS_POR_SETOR
                    salvar_dados(dados_sistema)
                    st.success(f"Planilha '{nome_planilha}' vinculada ao setor '{setor_dest}' com sucesso!")
                    st.rerun()

        with tab_cadastrar_usr:
            st.markdown("### Cadastrar Novo Usuário e Definir Acessos")
            novo_login = st.text_input("Login (ex: joao)").strip().lower()
            nova_senha = st.text_input("Senha Inicial").strip()
            nome_completo = st.text_input("Nome Exibido").strip()
            
            # Escolha exata de quais setores este usuário pode acessar
            todos_setores = ["Visão Geral"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]
            setores_usuario = st.multiselect("Selecione os Setores que esta pessoa terá permissão para visualizar:", todos_setores, default=["Visão Geral"])
            e_admin_check = st.checkbox("Tornar Administrador do Sistema")

            if st.button("👤 Salvar Usuário"):
                if novo_login and nova_senha and nome_completo and setores_usuario:
                    USUARIOS[novo_login] = {
                        "senha": nova_senha,
                        "nome": nome_completo,
                        "setores": setores_usuario,
                        "e_admin": e_admin_check
                    }
                    dados_sistema["usuarios"] = USUARIOS
                    salvar_dados(dados_sistema)
                    st.success(f"Usuário '{novo_login}' cadastrado com acesso aos setores: {', '.join(setores_usuario)}!")
                    st.rerun()

        with tab_gerenciar_usr:
            st.markdown("### Gerenciar Usuários e Alterar Visibilidade de Setores")
            todos_setores = ["Visão Geral"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]

            for login, info in list(USUARIOS.items()):
                with st.expander(f"👤 **{info['nome']}** (`{login}`)", expanded=False):
                    col_perm, col_botoes = st.columns([3, 1])
                    
                    with col_perm:
                        novos_setores = st.multiselect(
                            f"Setores com visibilidade liberada para {login}:",
                            options=todos_setores,
                            default=info["setores"],
                            key=f"ms_setores_{login}"
                        )
                    
                    with col_botoes:
                        st.write("")
                        st.write("")
                        if st.button("💾 Atualizar Acessos", key=f"btn_update_{login}"):
                            USUARIOS[login]["setores"] = novos_setores
                            dados_sistema["usuarios"] = USUARIOS
                            salvar_dados(dados_sistema)
                            st.success("Permissões atualizadas!")
                            st.rerun()
                            
                        if login != st.session_state["usuario_logado"]:
                            if st.button("🗑️ Excluir Usuário", key=f"btn_del_{login}"):
                                del USUARIOS[login]
                                dados_sistema["usuarios"] = USUARIOS
                                salvar_dados(dados_sistema)
                                st.rerun()

    # --- OPERAÇÃO DE PLANILHAS ---
    else:
        planilhas_do_setor = PLANILHAS_POR_SETOR.get(setor_selecionado, {})
        
        with c_planilha:
            if planilhas_do_setor:
                planilha_selecionada = st.selectbox("📁 Planilha", list(planilhas_do_setor.keys()))
                id_planilha = planilhas_do_setor[planilha_selecionada]
            else:
                st.selectbox("📁 Planilha", ["Nenhuma planilha cadastrada neste setor"], disabled=True)
                id_planilha = None
            
        with c_modo:
            modo_visualizacao = st.radio(
                "🖥️ Modo de Exibição", 
                ["🌐 Google Sheets Oficial (Completo)", "⚡ Tabela Nativa (API Rápida)"],
                horizontal=True
            )

        with c_user:
            st.write(f"👤 **{dados_usuario['nome']}**")
            if st.button("🚪 Sair", key="btn_logout"):
                st.session_state["usuario_logado"] = None
                st.rerun()

        if id_planilha:
            # MODO 1: GOOGLE SHEETS OFICIAL
            if modo_visualizacao == "🌐 Google Sheets Oficial (Completo)":
                embed_url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/edit"
                st.components.v1.html(
                    f'<iframe src="{embed_url}" width="100%" height="860" frameborder="0" style="border:1px solid #333; border-radius:8px;"></iframe>',
                    height=865
                )
            
            # MODO 2: EDIÇÃO RÁPIDA VIA API
            else:
                df_dados = ler_planilha_api(id_planilha)
                if df_dados is not None:
                    st.caption("⚡ **Modo Nativo via API**: Edite os valores na tabela e clique em salvar.")
                    df_editado = st.data_editor(df_dados, use_container_width=True, height=650, num_rows="dynamic")
                    
                    col_salvar, col_vazio = st.columns([1, 3])
                    with col_salvar:
                        if st.button("💾 Salvar Alterações na Nuvem"):
                            if salvar_alteracoes_api(id_planilha, df_editado):
                                st.success("Planilha sincronizada com sucesso!")
                                st.rerun()
                else:
                    st.warning("Não foi possível carregar via API. Verifique as credenciais da Service Account.")
        else:
            st.info("Nenhuma planilha vinculada a este setor.")
