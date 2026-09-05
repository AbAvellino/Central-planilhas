import streamlit as st
import pandas as pd
import json
import os
import hashlib
from datetime import datetime
import io
import gspread
from google.oauth2.service_account import Credentials
import psycopg2
from psycopg2.extras import RealDictCursor

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
# FUNÇÕES DE CRIPTOGRAFIA
# ==============================================================================
def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def verificar_senha(senha_input: str, senha_hash: str) -> bool:
    return hash_senha(senha_input) == senha_hash

# ==============================================================================
# CONEXÃO E OPERAÇÕES BANCO DE DADOS POSTGRESQL (COM CACHE)
# ==============================================================================
@st.cache_resource
def criar_conexao_db_cache():
    try:
        db_url = st.secrets["postgres"]["url"]
        return psycopg2.connect(db_url)
    except Exception as e:
        st.error(f"⚠️ Erro ao conectar ao Banco de Dados PostgreSQL: {e}")
        return None

def obter_conexao_db():
    conn = criar_conexao_db_cache()
    if conn is None or conn.closed != 0:
        st.cache_resource.clear()
        conn = criar_conexao_db_cache()
    return conn

def inicializar_banco():
    conn = obter_conexao_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Tabela de Usuários
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                login VARCHAR(50) PRIMARY KEY,
                senha VARCHAR(128) NOT NULL,
                nome VARCHAR(100) NOT NULL,
                setores TEXT[] NOT NULL,
                permissao VARCHAR(20) NOT NULL,
                e_admin BOOLEAN DEFAULT FALSE
            );
        """)
        
        # Tabela de Planilhas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS planilhas (
                id SERIAL PRIMARY KEY,
                setor VARCHAR(50) NOT NULL,
                nome VARCHAR(100) NOT NULL,
                spreadsheet_id VARCHAR(128) NOT NULL,
                UNIQUE(setor, nome)
            );
        """)

        # Tabela de Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario VARCHAR(50) NOT NULL,
                acao VARCHAR(100) NOT NULL,
                detalhe TEXT
            );
        """)

        conn.commit()

        # Criar Usuário Admin Padrão se não existir nenhum (com ON CONFLICT para evitar erro)
        cursor.execute("""
            INSERT INTO usuarios (login, senha, nome, setores, permissao, e_admin)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (login) DO NOTHING;
        """, (
            "admin",
            hash_senha("123"),
            "Gerência / Admin",
            ["Visão Geral", "Busca Global", "Almoxarifado", "Containers", "Painel Admin"],
            "Escrita",
            True
        ))
        
        # Inserir planilhas iniciais padrão
        cursor.execute("""
            INSERT INTO planilhas (setor, nome, spreadsheet_id) VALUES
            ('Almoxarifado', 'Controle', '1nb-gVt6e98Kh4BAYl9l-dgspleRHZDfe8DAT2B1OB_I'),
            ('Almoxarifado', 'Ferro Quantidade', '1kyrYqJoJLyaL8fvCFVvnFgAbEHIAv6h1W2ZHt1Hmhn4'),
            ('Containers', 'Controle de containers em patio', '1Im_QMBgD1GYDSe6v4-xvN6rOHUAGTZjA-fl3hB1w5tg')
            ON CONFLICT DO NOTHING;
        """)
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao inicializar banco: {e}")

# Executa a inicialização do banco
inicializar_banco()

def carregar_usuarios():
    conn = obter_conexao_db()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM usuarios;")
        rows = cursor.fetchall()
        cursor.close()

        usuarios = {}
        for r in rows:
            usuarios[r["login"]] = {
                "senha": r["senha"],
                "nome": r["nome"],
                "setores": r["setores"],
                "permissao": r["permissao"],
                "e_admin": r["e_admin"]
            }
        return usuarios
    except Exception as e:
        conn.rollback()
        return {}

def carregar_planilhas_por_setor():
    conn = obter_conexao_db()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM planilhas;")
        rows = cursor.fetchall()
        cursor.close()

        planilhas_dict = {}
        for r in rows:
            setor = r["setor"]
            if setor not in planilhas_dict:
                planilhas_dict[setor] = {}
            planilhas_dict[setor][r["nome"]] = r["spreadsheet_id"]
        return planilhas_dict
    except Exception as e:
        conn.rollback()
        return {}

def registrar_log(usuario, acao, detalhe):
    conn = obter_conexao_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (usuario, acao, detalhe)
            VALUES (%s, %s, %s);
        """, (usuario, acao, detalhe))
        conn.commit()
        cursor.close()
    except Exception:
        conn.rollback()

def obter_logs():
    conn = obter_conexao_db()
    if not conn:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query("SELECT data_hora, usuario, acao, detalhe FROM logs ORDER BY id DESC LIMIT 200;", conn)
        return df
    except Exception:
        conn.rollback()
        return pd.DataFrame()

# Carrega dados do banco
USUARIOS = carregar_usuarios()
PLANILHAS_POR_SETOR = carregar_planilhas_por_setor()

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
        st.error(f"⚠️ Erro ao conectar na API do Google: {e}")
        return None

client_gspread = conectar_google_api()

@st.cache_data(ttl=120)
def obter_abas_planilha(spreadsheet_id):
    if not client_gspread:
        return []
    try:
        sh = client_gspread.open_by_key(spreadsheet_id)
        return [ws.title for ws in sh.worksheets()]
    except Exception:
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
                with st.spinner("Autenticando..."):
                    if usuario in USUARIOS:
                        senha_armazenada = USUARIOS[usuario]["senha"]
                        
                        if verificar_senha(senha, senha_armazenada) or (senha == senha_armazenada):
                            st.session_state["usuario_logado"] = usuario
                            registrar_log(usuario, "Login", "Usuário autenticado no PostgreSQL")
                            st.rerun()
                        else:
                            st.error("Senha incorreta.")
                    else:
                        st.error("Usuário não encontrado.")

else:
    dados_usuario = USUARIOS[st.session_state["usuario_logado"]]
    setores_permitidos = dados_usuario["setores"]
    
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

    # --- BUSCA GLOBAL ---
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
        st.subheader("⚙️ Painel do Administrador & Logs de Auditoria (PostgreSQL)")

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

            if st.button("💾 Salvar Planilha no Banco"):
                if setor_dest and nome_planilha and id_planilha_input:
                    with st.spinner("Gravando no PostgreSQL..."):
                        conn = obter_conexao_db()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO planilhas (setor, nome, spreadsheet_id)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (setor, nome) DO UPDATE SET spreadsheet_id = EXCLUDED.spreadsheet_id;
                                """, (setor_dest, nome_planilha, id_planilha_input))
                                conn.commit()
                                cursor.close()

                                registrar_log(st.session_state["usuario_logado"], "Cadastro Planilha", f"Planilha '{nome_planilha}' no setor '{setor_dest}'")
                                st.success("Planilha gravada no PostgreSQL com sucesso!")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao salvar planilha: {e}")

        with tab_cadastrar_usr:
            st.markdown("### Cadastrar Novo Usuário")
            novo_login = st.text_input("Login (ex: joao)").strip().lower()
            nova_senha = st.text_input("Senha Inicial", type="password").strip()
            nome_completo = st.text_input("Nome Exibido").strip()
            
            todos_setores = ["Visão Geral", "Busca Global"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]
            setores_usuario = st.multiselect("Setores Permitidos:", todos_setores, default=["Visão Geral", "Busca Global"])
            permissao_tipo = st.radio("Nível de Acesso às Planilhas:", ["Escrita", "Leitura"], horizontal=True)
            e_admin_check = st.checkbox("Tornar Administrador do Sistema")

            if st.button("👤 Salvar Usuário no Banco"):
                if novo_login and nova_senha and nome_completo and setores_usuario:
                    if novo_login in USUARIOS:
                        st.error(f"O login '{novo_login}' já está cadastrado. Escolha outro login.")
                    else:
                        with st.spinner("Criando usuário no PostgreSQL..."):
                            conn = obter_conexao_db()
                            if conn:
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        INSERT INTO usuarios (login, senha, nome, setores, permissao, e_admin)
                                        VALUES (%s, %s, %s, %s, %s, %s)
                                        ON CONFLICT (login) DO UPDATE SET 
                                            senha = EXCLUDED.senha,
                                            nome = EXCLUDED.nome,
                                            setores = EXCLUDED.setores,
                                            permissao = EXCLUDED.permissao,
                                            e_admin = EXCLUDED.e_admin;
                                    """, (novo_login, hash_senha(nova_senha), nome_completo, setores_usuario, permissao_tipo, e_admin_check))
                                    conn.commit()
                                    cursor.close()

                                    registrar_log(st.session_state["usuario_logado"], "Cadastro Usuário", f"Usuário '{novo_login}' criado/atualizado.")
                                    st.success(f"Usuário '{novo_login}' gravado no banco com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro ao cadastrar usuário: {e}")

        with tab_gerenciar_usr:
            st.markdown("### Gerenciar Usuários no Banco")
            todos_setores = ["Visão Geral", "Busca Global"] + list(PLANILHAS_POR_SETOR.keys()) + ["Painel Admin"]

            for login, info in list(USUARIOS.items()):
                with st.expander(f"👤 **{info['nome']}** (`login: {login}`)", expanded=False):
                    c_n, c_s = st.columns(2)
                    with c_n:
                        novo_nome_val = st.text_input("Nome do Usuário", value=info["nome"], key=f"nome_{login}")
                    with c_s:
                        nova_senha_val = st.text_input("Nova Senha (deixe em branco para manter)", type="password", key=f"pwd_{login}")

                    c_perm1, c_perm2, c_admin = st.columns([2, 1, 1])
                    with c_perm1:
                        novos_setores = st.multiselect("Setores liberados:", options=todos_setores, default=info["setores"], key=f"ms_{login}")
                    with c_perm2:
                        nova_perm = st.selectbox("Modo de Acesso:", ["Escrita", "Leitura"], index=0 if info.get("permissao","Escrita") == "Escrita" else 1, key=f"perm_{login}")
                    with c_admin:
                        e_admin_val = st.checkbox("É Admin", value=info.get("e_admin", False), key=f"chk_admin_{login}")

                    st.markdown("---")
                    c_btn_save, c_btn_del = st.columns([2, 1])
                    
                    with c_btn_save:
                        if st.button("💾 Salvar no Banco", key=f"btn_up_{login}"):
                            with st.spinner("Atualizando usuário..."):
                                conn = obter_conexao_db()
                                if conn:
                                    try:
                                        cursor = conn.cursor()
                                        if nova_senha_val.strip():
                                            cursor.execute("""
                                                UPDATE usuarios SET nome=%s, senha=%s, setores=%s, permissao=%s, e_admin=%s WHERE login=%s;
                                            """, (novo_nome_val, hash_senha(nova_senha_val.strip()), novos_setores, nova_perm, e_admin_val, login))
                                        else:
                                            cursor.execute("""
                                                UPDATE usuarios SET nome=%s, setores=%s, permissao=%s, e_admin=%s WHERE login=%s;
                                            """, (novo_nome_val, novos_setores, nova_perm, e_admin_val, login))
                                        conn.commit()
                                        cursor.close()

                                        registrar_log(st.session_state["usuario_logado"], "Alteração Usuário", f"Usuário '{login}' atualizado no PostgreSQL")
                                        st.success(f"Usuário '{login}' atualizado!")
                                        st.rerun()
                                    except Exception as e:
                                        conn.rollback()
                                        st.error(f"Erro ao atualizar: {e}")
                    
                    with c_btn_del:
                        if st.button("❌ Excluir", key=f"btn_del_{login}", type="secondary"):
                            if login == st.session_state["usuario_logado"]:
                                st.error("Você não pode excluir o seu próprio usuário logado!")
                            else:
                                with st.spinner("Removendo usuário..."):
                                    conn = obter_conexao_db()
                                    if conn:
                                        try:
                                            cursor = conn.cursor()
                                            cursor.execute("DELETE FROM usuarios WHERE login=%s;", (login,))
                                            conn.commit()
                                            cursor.close()

                                            registrar_log(st.session_state["usuario_logado"], "Exclusão Usuário", f"Usuário '{login}' removido do banco")
                                            st.warning(f"Usuário '{login}' removido!")
                                            st.rerun()
                                        except Exception as e:
                                            conn.rollback()
                                            st.error(f"Erro ao excluir: {e}")

        with tab_logs:
            st.markdown("### 📜 Histórico de Atividades / Auditoria (PostgreSQL)")
            df_logs = obter_logs()
            if not df_logs.empty:
                st.dataframe(df_logs, use_container_width=True)
            else:
                st.info("Nenhum log registrado ainda.")

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

        st.markdown("---")

        if id_planilha:
            if modo_visualizacao == "🌐 Google Sheets Oficial (Completo)":
                embed_url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/edit"
                st.components.v1.html(
                    f'<iframe src="{embed_url}" width="100%" height="750" frameborder="0" style="border:1px solid #333; border-radius:8px;"></iframe>',
                    height=755
                )
            
            else:
                with st.spinner("Carregando abas da planilha..."):
                    abas = obter_abas_planilha(id_planilha)
                
                aba_selecionada = None
                
                c_aba, c_exp = st.columns([2, 2])
                with c_aba:
                    if abas:
                        aba_selecionada = st.selectbox("📑 Selecione a Aba da Planilha:", abas)
                
                with st.spinner("Buscando dados da planilha via API..."):
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
                                with st.spinner("Enviando alterações para o Google Sheets..."):
                                    if salvar_alteracoes_api(id_planilha, df_editado, aba_selecionada):
                                        registrar_log(
                                            st.session_state["usuario_logado"], 
                                            "Edição Planilha", 
                                            f"Planilha '{planilha_selecionada}' (Aba: '{aba_selecionada}') atualizada"
                                        )
                                        st.success("Planilha sincronizada e alteração registrada nos Logs!")
                                        st.rerun()
                    
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
