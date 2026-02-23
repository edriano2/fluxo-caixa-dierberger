import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Configuração da página
st.set_page_config(
    page_title="Fluxo de Caixa Dierberger", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Barra Lateral
with st.sidebar:
    st.header("⚙️ Configurações")
    caminho_input = st.text_input("Caminho do Ficheiro:", r'C:\DIERBERGER\BASE FC GRUPO.xlsx')
    
    @st.cache_data(show_spinner=False)
    def listar_abas(caminho):
        try:
            xl = pd.ExcelFile(caminho, engine='openpyxl')
            return xl.sheet_names
        except:
            return []

    abas_disponiveis = listar_abas(caminho_input)
    index_default = abas_disponiveis.index("BASE_FC") if "BASE_FC" in abas_disponiveis else 0
    aba_selecionada = st.selectbox("Selecione a Aba:", abas_disponiveis, index=index_default) if abas_disponiveis else "BASE_FC"

    st.divider()
    container_filtro = st.container()

    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

# 1. CARREGAMENTO E NORMALIZAÇÃO DE DADOS
@st.cache_data(ttl=60, show_spinner="Processando Colunas...")
def carregar_dados_especificos(caminho, aba):
    try:
        df = pd.read_excel(caminho, sheet_name=aba, engine='openpyxl')
        
        # Normalizar nomes das colunas
        cols_map = {str(c).strip().upper(): str(c) for c in df.columns}
        
        # Mapeamento inteligente
        col_data = cols_map.get("VENCTO REAL")
        col_val = cols_map.get("SALDO FC") or cols_map.get("SALDO")
        col_nat = cols_map.get("CRÉDITOS/DÉBITOS")
        col_cat = cols_map.get("NATUREZA RESUMIDA") or cols_map.get("NOME NATUREZA")
        
        missing = []
        if not col_data: missing.append("Vencto Real")
        if not col_val: missing.append("Saldo / SALDO FC")
        if not col_nat: missing.append("Créditos/Débitos")
        
        if missing:
            st.error(f"⚠️ Colunas obrigatórias não encontradas: {', '.join(missing)}")
            return None
        
        df_work = pd.DataFrame({
            'Data': pd.to_datetime(df[col_data], errors='coerce'),
            'Natureza_Tipo': df[col_nat].astype(str),
            'Valor_Bruto': pd.to_numeric(df[col_val], errors='coerce'),
            'Categoria': df[col_cat].astype(str) if col_cat else "Geral"
        })
        
        return df_work.dropna(subset=['Data', 'Valor_Bruto'])
    except Exception as e:
        st.error(f"⚠️ Erro ao ler Excel: {e}")
        return None

df_base = carregar_dados_especificos(caminho_input, aba_selecionada)

if df_base is not None and not df_base.empty:
    
    # --- FILTRO DE DATA ---
    data_min_base = df_base['Data'].min().to_pydatetime()
    data_max_base = df_base['Data'].max().to_pydatetime()
    
    with container_filtro:
        st.subheader("📅 Período de Análise")
        hoje = datetime.now()
        inicio_padrao = datetime(hoje.year, hoje.month, 1)
        if inicio_padrao < data_min_base: inicio_padrao = data_min_base
        
        periodo = st.date_input("Selecione o intervalo:", value=(inicio_padrao, data_max_base))

    if isinstance(periodo, tuple) and len(periodo) == 2:
        d_inicio, d_fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
        
        def aplicar_sinal_manual(nat_texto, valor):
            txt = str(nat_texto).lower()
            if valor < 0: return valor
            if any(x in txt for x in ['débito', 'debito', 'saída', 'saida']):
                return -abs(valor)
            return abs(valor)

        # Processamento
        df_atrasados = df_base[df_base['Data'] < d_inicio].copy()
        df_no_periodo = df_base[(df_base['Data'] >= d_inicio) & (df_base['Data'] <= d_fim)].copy()
        
        # Cálculo de Atrasados
        if not df_atrasados.empty:
            df_atrasados['Valor_Sinal'] = [
                aplicar_sinal_manual(n, v) for n, v in zip(df_atrasados['Natureza_Tipo'], df_atrasados['Valor_Bruto'])
            ]
            total_atrasado = df_atrasados['Valor_Sinal'].sum()
            
            # Cálculo da Média de Atraso em dias
            hoje_dt = pd.Timestamp(datetime.now().date())
            df_atrasados['Dias_Atraso'] = (hoje_dt - df_atrasados['Data']).dt.days
            media_dias_atraso = df_atrasados['Dias_Atraso'].mean()
        else:
            total_atrasado = 0
            media_dias_atraso = 0
            
        # Cálculo do Período
        if not df_no_periodo.empty:
            df_no_periodo['Valor_Sinal'] = [
                aplicar_sinal_manual(n, v) for n, v in zip(df_no_periodo['Natureza_Tipo'], df_no_periodo['Valor_Bruto'])
            ]
            df_display = df_no_periodo
        else:
            df_display = pd.DataFrame(columns=['Data', 'Natureza_Tipo', 'Valor_Bruto', 'Categoria', 'Valor_Sinal'])
            
    else:
        st.warning("Selecione as datas de início e fim.")
        st.stop()

    # --- MÉTRICAS ---
    saldo_inicial_banco = 45250.80
    entradas_f = df_display[df_display['Valor_Sinal'] > 0]['Valor_Sinal'].sum() if not df_display.empty else 0
    saidas_f = abs(df_display[df_display['Valor_Sinal'] < 0]['Valor_Sinal'].sum()) if not df_display.empty else 0
    
    # O Saldo Final agora considera: Banco + Atrasados + Movimentação do Período
    saldo_final = saldo_inicial_banco + total_atrasado + entradas_f - saidas_f

    # --- INTERFACE ---
    st.title("📊 Fluxo de Caixa Dierberger")
    st.caption(f"Ficheiro: {caminho_input.split('\\')[-1]} | Aba: {aba_selecionada}")

    # Layout com colunas para incluir métricas
    m1, m2, m3, m4, m5 = st.columns(5)
    
    m1.metric("Saldo em Banco", f"R$ {saldo_inicial_banco:,.2f}", help="Saldo inicial fixo de conta corrente.")
    
    cor_atrasado = "normal" if total_atrasado >= 0 else "inverse"
    m2.metric("Total Atrasados", f"R$ {total_atrasado:,.2f}", 
              delta=f"{total_atrasado:,.2f}", 
              delta_color=cor_atrasado,
              help="Soma de todos os lançamentos com vencimento anterior à data inicial selecionada.")
    
    m3.metric("Entradas (Período)", f"R$ {entradas_f:,.2f}")
    m4.metric("Saídas (Período)", f"R$ {saidas_f:,.2f}")
    
    m5.metric("Saldo Final Previsto", f"R$ {saldo_final:,.2f}", 
              help="Cálculo: Saldo Banco + Atrasados + Entradas - Saídas")

    # Novo Resumo Específico para Atraso Médio
    st.write("---")
    c_atraso1, c_atraso2 = st.columns([1, 4])
    with c_atraso1:
        st.metric("Média Dias Atraso", f"{media_dias_atraso:.1f} dias", 
                  help="Média de dias decorridos desde o vencimento original até hoje para os itens em atraso.")
    with c_atraso2:
        if not df_atrasados.empty:
            max_atraso = df_atrasados['Dias_Atraso'].max()
            st.info(f"🚩 O item com maior atraso está pendente há **{max_atraso} dias**.")

    st.divider()

    # Gráfico
    if not df_display.empty:
        st.subheader("📈 Movimentação Diária (No Período)")
        df_display['Tipo'] = ['Crédito' if x > 0 else 'Débito' for x in df_display['Valor_Sinal']]
        df_plot = df_display.groupby(['Data', 'Tipo'])['Valor_Sinal'].sum().abs().unstack().fillna(0)
        
        fig = go.Figure()
        if 'Crédito' in df_plot.columns:
            fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Crédito'], name='Entradas', marker_color='#10b981'))
        if 'Débito' in df_plot.columns:
            fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Débito'], name='Saídas', marker_color='#ef4444'))
        
        fig.update_layout(barmode='group', height=350, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    # Detalhes
    t1, t2, t3 = st.tabs(["📊 Resumo por Categoria", "📝 Movimentação do Período", "⚠️ Detalhe de Atrasados"])
    
    with t1:
        if not df_display.empty:
            resumo = df_display.groupby('Categoria')['Valor_Sinal'].sum().sort_index()
            st.table(resumo)
    
    with t2:
        if not df_display.empty:
            st.dataframe(df_display.sort_values('Data'), use_container_width=True)
            
    with t3:
        if not df_atrasados.empty:
            st.error(f"Existem {len(df_atrasados)} lançamentos pendentes anteriores a {d_inicio.strftime('%d/%m/%Y')}")
            # Adicionando a coluna de dias de atraso na visualização detalhada
            st.dataframe(df_atrasados[['Data', 'Natureza_Tipo', 'Valor_Bruto', 'Valor_Sinal', 'Categoria', 'Dias_Atraso']].sort_values('Dias_Atraso', ascending=False), use_container_width=True)
        else:
            st.success("Não existem valores em atraso para o período selecionado.")
else:
    st.warning("Nenhum dado encontrado. Verifique o caminho do ficheiro e o nome da aba.")