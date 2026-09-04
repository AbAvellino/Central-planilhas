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
# FUNÇÕES DE CRIPTOGRAFIA DE SENHA
# ==============================================================================
def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def verificar_senha(senha_input: str, senha_hash: str) -> bool:
    return hash_senha(senha_input) == senha_hash

# ==============================================================================
# PERSISTÊNCIA LOCAL (DADOS, USUÁRIOS E LOGS)
# ==============================================================================
ARQUIVO_DADOS = "dados_sistema.json"
ARQUIVO_LOGS = "logs_sistema.json"

DADOS_INICIAIS = {
    "usuarios": {
        "admin": {
            "senha": hash_senha("123"),
            "nome": "Gerência / Admin",
            "setores": ["Visão Geral", "Busca Global", "Almoxarifado", "Containers", "Painel Admin"],
            "permissao": "Escrita",
            "e_admin": True
        },
        "almoxarife": {
            "senha": hash_senha("456"),
            "nome": "Operador de Almoxarifado",
            "setores": ["Visão Geral", "Almoxarifado"],
            "permissao": "Escrita",
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

def registrar_log(usuario, acao, detalhe):
    logs = []
    if os.path.exists(ARQUIVO_LOGS):
        with open(ARQUIVO_LOGS, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except:
                logs = []
    
    novo_registro = {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": usuario,
        "acao": acao,
        "detalhe": detalhe
    }
    logs.insert(0, novo_registro) # Mais recentes primeiro
    with open(ARQUIVO_LOGS, "w", encoding="utf-8") as f:
        json.dump(logs[:200], f, ensure_ascii=False, indent=4) # Mantém os últimos 200 logs

dados_sistema = carregar_dados()
USUARIOS = dados_sistema["usuarios"]
PLANILHAS_POR_SETOR = dados_sistema["planilhas"]

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

@st.cache_data(ttl=120)
def obter_abas_planilha(spreadsheet_id):
    if not client_gspread:
        return []
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        return [ws.title for ws in sh.worksheets()]
    except Exception as e:
        return []

@st.cache_data(ttl=120)
def ler_planilha_api(spreadsheet_id, nome_aba=None):
    if not client_gspread:
        return None
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        sheet = sh.worksheet(nome_aba) if nome_aba else sh.sheet1
        dados = sheet.get_all_records()
        return pd.DataFrame(dados)
    except Exception as e:
        st.error(f"Erro ao acessar planilha/aba via API: {e}")
        return None

def salvar_alteracoes_api(spreadsheet_id, df_atualizado, nome_aba=None):
    if not client_gspread:
        return False
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
                    
                    # Compatibilidade: verifica se a senha é o hash ou se ainda está em texto puro no JSON antigo
                    senha_valida = verificar_senha(senha, senha_armazenada) or (senha == senha_armazenada)
                    
                    if senha_valida:
                        # Se ainda estava em texto puro, atualiza automaticamente para o hash seguro
                        if senha == senha_armazenada:
                            USUARIOS[usuario]["senha"] = hash_senha(senha)
                            dados_sistema["usuarios"] = USUARIOS
                            salvar_dados(dados_sistema)

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
            "📋 Gerenciar Permissões",
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
                    dados_sistema["planilhas"] = PLANILHAS_POR_SETOR
                    salvar_dados(dados_sistema)
                    registrar_log(st.session_state["usuario_logado"], "Cadastro Planilha", f"Planilha '{nome_planilha}' no setor '{setor_dest}'")
                    st.success("Planilha salva com sucesso!")
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
                    dados_sistema["usuarios"] = USUARIOS
                    salvar_dados(dados_sistema)
                    registrar_log(st.session_state["usuario_logado"], "Cadastro Usuário", f"Usuário '{novo_login}' criado.")
                    st.success(f"Usuário '{novo_login}' cadastrado de forma segura!")
                    st.rerun()

        with tab_gerenciar_usr:
            st.markdown("### Gerenciar Acessos e Permissões")
            todos_setores = ["Visão Geral", "Busca Global"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]

            for login, info in list(USUARIOS.items()):
                with st.expander(f"👤 **{info['nome']}** (`{login}`)", expanded=False):
                    c_perm1, c_perm2, c_act = st.columns([2, 1, 1])
                    with c_perm1:
                        novos_setores = st.multiselect("Setores liberados:", options=todos_setores, default=info["setores"], key=f"ms_{login}")
                    with c_perm2:
                        nova_perm = st.selectbox("Modo de Acesso:", ["Escrita", "Leitura"], index=0 if info.get("permissao","Escrita") == "Escrita" else 1, key=f"perm_{login}")
                    with c_act:
                        st.write("")
                        st.write("")
                        if st.button("💾 Atualizar", key=f"btn_up_{login}"):
                            USUARIOS[login]["setores"] = novos_setores
                            USUARIOS[login]["permissao"] = nova_perm
                            dados_sistema["usuarios"] = USUARIOS
                            salvar_dados(dados_sistema)
                            registrar_log(st.session_state["usuario_logado"], "Alteração Permissão", f"Acessos do usuário '{login}' atualizados")
                            st.success("Atualizado!")
                            st.rerun()

        with tab_logs:
            st.markdown("### 📜 Histórico de Atividades / Auditoria")
            if os.path.exists(ARQUIVO_LOGS):
                with open(ARQUIVO_LOGS, "r", encoding="utf-8") as f:
                    logs_data = json.load(f)
                df_logs = pd.DataFrame(logs_data)
                st.dataframe(df_logs, use_container_width=True)
            else:
                st.info("Nenhum log registrado ainda.")

    # --- OPERAÇÃO DE PLANILHAS (VISUALIZAÇÃO E EDIÇÃO MULTIABAS) ---
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

        st.markdown("---")

        if id_planilha:
            # MODO 1: GOOGLE SHEETS OFICIAL
            if modo_visualizacao == "🌐 Google Sheets Oficial (Completo)":
                embed_url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/edit"
                st.components.v1.html(
                    f'<iframe src="{embed_url}" width="100%" height="750" frameborder="0" style="border:1px solid #333; border-radius:8px;"></iframe>',
                    height=755
                )
            
            # MODO 2: EDIÇÃO RÁPIDA VIA API MULTIABAS
            else:
                abas = obter_abas_planilha(id_planilha)
                aba_selecionada = None
                
                c_aba, c_exp = st.columns([2, 2])
                with c_aba:
                    if abas:
                        aba_selecionada = st.selectbox("📑 Selecione a Aba da Planilha:", abas)
                
                df_dados = ler_planilha_api(id_planilha, aba_selecionada)
                
                if df_dados is not None:
                    pode_editar = (dados_usuario.get("permissao", "Escrita") == "Escrita")
                    
                    if not pode_editar:
                        st.info("ℹ️ Você possui acesso em **Modo de Somente Leitura** nesta planilha.")
                    
                    df_editado = st.data_editor(
                        df_dados, 
                        use_container_width=True, 
                        height=550, 
                        num_rows="dynamic" if pode_editar else "fixed",
                        disabled=not pode_editar
                    )
                    
                    col_salvar, col_csv, col_excel = st.columns([1.5, 1, 1])
                    
                    if pode_editar:
                        with col_salvar:
                            if st.button("💾 Salvar Alterações na Nuvem"):
                                if salvar_alteracoes_api(id_planilha, df_editado, aba_selecionada):
                                    registrar_log(
                                        st.session_state["usuario_logado"], 
                                        "Edição Planilha", 
                                        f"Planilha '{planilha_selecionada}' (Aba: '{aba_selecionada}') atualizada"
                                    )
                                    st.success("Planilha sincronizada e alteração registrada nos Logs!")
                                    st.rerun()
                    
                    # OPÇÕES DE EXPORTAÇÃO DE DADOS
                    with col_csv:
                        csv_data = df_editado.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Exportar CSV", data=csv_data, file_name=f"{planilha_selecionada}.csv", mime="text/csv")
                    
                    with col_excel:
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df_editado.to_excel(writer, index=False, sheet_name=aba_selecionada or "Dados")
                        st.download_button("📊 Exportar Excel", data=buffer.getvalue(), file_name=f"{planilha_selecionada}.xlsx", mime="application/vnd.ms-excel")
                else:
                    st.warning("Não foi possível carregar via API. Verifique as credenciais da Service Account.")
        else:
            st.info("Nenhuma planilha vinculada a este setor.")
