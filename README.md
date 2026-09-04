# 📊 Central Unificada de Planilhas (Streamlit + Google Sheets API)

Uma plataforma web de gestão centralizada desenvolvida em **Python** e **Streamlit**, integrada via **Google Sheets API**. O sistema permite visualizar, editar, filtrar e gerenciar múltiplas planilhas do Google Sheets divididas por setores, com controle de acesso baseado em funções (RBAC), criptografia de senhas e auditoria completa de ações via logs.

---

## 🚀 Funcionalidades Principais

* **🔒 Autenticação e Segurança:**
  * Login individual com criptografia **SHA-256** para armazenamento seguro de senhas.
  * Controle de acesso por **Setores/Áreas**.
  * Permissões granulares de acesso: **Escrita** (edição completa) ou **Leitura** (somente visualização/download).
* **🏢 Gestão Multisetor:**
  * Suporte a múltiplos setores (ex: Almoxarifado, Containers, Gerência, etc.).
  * Alternância dinâmica de abas (*worksheets*) dentro de cada planilha Google.
* **🖥️ Modos de Exibição:**
  * **Google Sheets Oficial:** Visualização incorporada (*iframe*) do painel nativo do Google.
  * **Tabela Nativa (API Rápida):** Interface reativa via `st.data_editor` para edições rápidas sem abrir a nuvem.
* **🔎 Busca Global Multisetor:**
  * Ferramenta de varredura que pesquisa palavras-chave, códigos de itens ou IDs simultaneamente em todas as planilhas cadastradas no sistema.
* **⚙️ Painel do Administrador:**
  * **Cadastro de Planilhas:** Adição simples de novas planilhas e novos setores via ID do Google Sheets.
  * **Cadastro de Usuários:** Criação de novos perfis com regras de acesso e privilégios específicos.
  * **Gerenciamento Completo de Usuários:** Edição de nomes, alteração de senhas, alteração de privilégios/setores e **exclusão com trava de segurança** (impede o admin de deletar o próprio perfil).
* **📜 Logs de Auditoria:**
  * Rastreamento automático de login, edições de dados, novos cadastros e exclusões de usuários com data e hora.
* **📥 Exportação de Dados:**
  * Download imediato das tabelas filtradas/editadas nos formatos **CSV** e **Excel (.xlsx)**.

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3.9+
* **Interface:** [Streamlit](https://streamlit.io/)
* **Manipulação de Dados:** Pandas
* **Integração Cloud:** `gspread`, `google-oauth2`
* **Exportação:** OpenPyXL

---

## 📋 Pré-requisitos

1. **Python 3.9+** instalado.
2. Conta no **Google Cloud Platform (GCP)** com as APIs ativadas:
   * **Google Sheets API**
   * **Google Drive API**
3. Uma **Conta de Serviço (Service Account)** criada no GCP com chave baixada no formato JSON (`chave.json`) ou configurada via `st.secrets`.

> ⚠️ **Importante:** Lembre-se de compartilhar cada planilha do Google Sheets com o e-mail da sua **Service Account** (concedendo permissão de *Editor*).

---

## 🔧 Instalação e Execução Local

### 1. Clonar o Repositório
```bash
git clone [https://github.com/seu-usuario/central-unificada-planilhas.git](https://github.com/seu-usuario/central-unificada-planilhas.git)
cd central-unificada-planilhas
