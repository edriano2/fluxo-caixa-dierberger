import streamlit as st
import pandas as pd
from datetime import datetime

# 1. Configuração da Página para o Streamlit Cloud
st.set_page_config(
    page_title="Fluxo de Caixa Dierberger", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Estilização visual dos cards (CSS Inline)
st.markdown("""
    <style>
    .stMetric { 
        background-color: #ffffff; 
        padding: 15px; 
        border-radius: 10px; 
        border: 1px solid #e2e8f0; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# 2. Link do SharePoint (Configurado para Download Direto)
# Este link substitui o caminho "C:\..." que causava erro na nuvem
URL_SHAREPOINT = "https://dierberger.sharepoint.com/:x:/g/G&A/Tesouraria/IQBvGITxDC6tTaCpk_9szr8xAU2-X0XOZVkGBIFPLwLvt88?download=1"

@st.cache_data(ttl=300, show_spinner="A atualizar dados do SharePoint...")
def carregar_dados(url):
    try:
        # Lê o Excel diretamente da nuvem usando o motor openpyxl
        df = pd.read_excel(url, engine='openpyxl')
        
        # Normaliza nomes de colunas (Maiúsculas e sem espaços extras)
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapeamento baseado nas colunas da sua planilha:
        # 'VENCTO REAL', 'SALDO FC', 'CRÉDITOS/DÉBITOS', 'NATUREZA RESUMIDA'
        col_data = 'VENCTO REAL'
        col_valor = 'SALDO FC'
        col_tipo = 'CRÉDITOS/DÉBITOS'
        col_cat = 'NATUREZA RESUMIDA'
        
        # Verifica se as colunas básicas existem para evitar erros
        if col_data not in df.columns or col_valor not in df.columns:
            st.error(f"Colunas não encontradas. Verificadas: {list(df.columns)}")
            return None

        # Criar DataFrame de trabalho limpo
        df_processado = pd.DataFrame({
            'Data': pd.to_datetime(df[col_data], errors='coerce'),
            'Valor_Bruto': pd.to_numeric(df[col_valor], errors='coerce'),
            'Tipo_Lancamento': df[col_tipo].astype(str).str.upper(),
            'Categoria': df[col_cat].astype(str)
        }).dropna(subset=['Data', 'Valor_Bruto'])
        
        # Lógica de Sinal (Resolve o ValueError das imagens anteriores)
        def aplicar_sinal(row):
            v = row['Valor_Bruto']
            t = row['Tipo_Lancamento']
            # Se for Débito (D), Saída (S) ou se o valor já for negativo, garantimos que seja negativo
            if 'D' in t or 'S' in t or v < 0:
                return -abs(v)
            return abs(v)
            
        df_processado['Valor_Final'] = df_processado.apply(aplicar_sinal, axis=1)
        return df_processado
        
    except Exception as e:
        st.error(f"Erro de conexão ou leitura: {e}")
        return None

# --- Interface do Dashboard ---
st.title("📊 Fluxo de Caixa - Dierberger")

dados = carregar_dados(URL_SHAREPOINT)

if dados is not None:
    # Configuração de Filtros na Barra Lateral
    hoje = datetime.now()
    inicio_mes = datetime(hoje.year, hoje.month, 1)
    
    with st.sidebar:
        st.header("⚙️ Filtros")
        # Seleção de intervalo de datas
        periodo = st.date_input("Período de Análise", [inicio_mes, dados['Data'].max()])
        
        if st.button("🔄 Forçar Atualização"):
            st.cache_data.clear()
            st.rerun()

    # Processamento dos Cards (se o período estiver selecionado)
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        d_de, d_ate = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
        
        df_mes = dados[(dados['Data'] >= d_de) & (dados['Data'] <= d_ate)]
        df_atraso = dados[dados['Data'] < d_de]
        
        # Cálculos Financeiros
        saldo_banco_inicial = 45250.80 
        atrasados = df_atraso['Valor_Final'].sum()
        entradas = df_mes[df_mes['Valor_Final'] > 0]['Valor_Final'].sum()
        saidas = df_mes[df_mes['Valor_Final'] < 0]['Valor_Final'].sum()
        saldo_projetado = saldo_banco_inicial + atrasados + entradas + saidas

        # Layout de Colunas para Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Saldo Inicial (Banco)", f"R$ {saldo_banco_inicial:,.2f}")
        c2.metric("Total Atrasados", f"R$ {atrasados:,.2f}", delta_color="inverse")
        c3.metric("Movimentação Mês", f"R$ {entradas + saidas:,.2f}")
        c4.metric("Projeção Final", f"R$ {saldo_projetado:,.2f}")
        
        st.divider()
        
        # Tabela de Resumo
        st.subheader("Resumo por Natureza")
        resumo = df_mes.groupby('Categoria')['Valor_Final'].sum().sort_index()
        st.table(resumo)
else:
    st.info("👋 Por favor, verifique se o ficheiro no SharePoint tem as permissões de partilha corretas.")
