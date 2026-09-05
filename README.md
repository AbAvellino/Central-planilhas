# 🏢 Central Unificada de Planilhas (Streamlit + PostgreSQL + Google Sheets)

Uma aplicação web desenvolvida em **Python** e **Streamlit** para gerenciamento centralizado de planilhas operacionais, controle de acessos por setor, busca global unificada e logs de auditoria.

---

## 🚀 O que há de novo (Últimas Atualizações)

- ⚡ **Busca Global Otimizada:** Varredura multisetor executada em paralelo (`ThreadPoolExecutor`), permitindo consultar múltiplos setores e planilhas em fração de segundos.
- 🎯 **Estabilidade Visual na Edição:** Resolução do comportamento de repaginação/pulo de tela (`scroll`) ao selecionar e editar células no `st.data_editor`, utilizando gerenciamento de chaves de estado do Streamlit.
- 🗄️ **Pool de Conexões de Banco de Dados:** Implementação do `ThreadedConnectionPool` no PostgreSQL (`psycopg2`) para alta eficiência e escalabilidade na autenticação e logs.
- 🧹 **Tratamento de Dados no Salvamento:** Sanitização de valores `NaN`/nulos e limpeza de caracteres invisíveis ao sincronizar com o Google Sheets API.

---

## 🛠️ Tecnologias Utilizadas

- **Interface:** Streamlit
- **Processamento de Dados:** Pandas / OpenPyXL
- **Banco de Dados:** PostgreSQL (Serviço de Logins, Permissões e Auditoria)
- **Integração de Planilhas:** Google Sheets API (`gspread` / `google-auth`)
- **Paralelismo:** Python `concurrent.futures`

---

## 🔒 Segurança e Permissões

- **Criptografia de Senhas:** Hashing via `SHA-256`.
- **Controle de Acesso em 2 Níveis:**
  - **Por Setor:** O usuário visualiza e edita apenas os setores atribuídos ao seu perfil.
  - **Por Nível de Acesso:** Definição entre privilégios de **Escrita** (edição direta e salvamento na nuvem) e **Leitura** (apenas visualização e exportação).
- **Painel Administrativo Restrito:** Exclusivo para usuários administradores realizarem novos cadastros, alterações de permissões e leitura dos **Logs de Auditoria**.

---

## 📑 Funcionalidades Principais

1. **🌐 Visualização Híbrida de Planilhas:**
   - **Modo Google Sheets Oficial:** Incorpora a interface original do Google Sheets via iframe.
   - **Modo Tabela Nativa (API Rápida):** Tabela nativa editável em alta velocidade com navegação por abas, salvamento na nuvem e exportação rápida em formato `.CSV` ou `.XLSX`.

2. **🔍 Busca Global Multisetor:**
   - Pesquisa avançada por códigos, descrições de produtos ou IDs de contêineres em todas as planilhas cadastradas no sistema simultaneamente.

3. **📜 Logs de Auditoria:**
   - Registro de todas as ações de usuários (Logins, Edições em Planilhas, Criação e Alteração de Usuários/Planilhas).

---

### 🔒 Gestão de Segredos e Segurança (`secrets.toml`)

A aplicação utiliza o recurso nativo `st.secrets` do Streamlit para o gerenciamento seguro de credenciais, garantindo que senhas e chaves de API nunca fiquem expostas no código fonte.

* **Conexão com PostgreSQL:** A string de conexão do banco de dados é injetada via variáveis de ambiente seguras.
* **Autenticação Google API:** É utilizada uma **Conta de Serviço (Service Account)** com escopo limitado (`https://www.googleapis.com/auth/spreadsheets`), garantindo acesso apenas às planilhas previamente autorizadas.
* **Boas Práticas de Repositório:** O arquivo `.streamlit/secrets.toml` está incluído no `.gitignore` para evitar o envio acidental de chaves privadas para repositórios de código.
