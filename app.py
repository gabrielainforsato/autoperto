import math
from datetime import date

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation


# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================

st.set_page_config(
    page_title="ManutCar",
    page_icon="🚗",
    layout="wide",
)


# =========================================================
# IDENTIDADE VISUAL
# =========================================================

st.markdown(
    """
    <style>
        .stApp {
            background: #F6F1DE;
        }

        [data-testid="stSidebar"] {
            background: #172313;
        }

        [data-testid="stSidebar"] * {
            color: #F6F1DE;
        }

        h1, h2, h3 {
            color: #172313;
        }

        .card {
            background: white;
            border-radius: 16px;
            padding: 18px;
            border-left: 6px solid #075A5A;
            box-shadow: 0 3px 12px #0002;
            margin: 10px 0;
        }

        div.stButton > button {
            border-radius: 12px;
            font-weight: 700;
        }

        .logo {
            font-size: 28px;
            font-weight: 800;
            color: #F6F1DE;
        }

        .sub {
            color: #B9B39A;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DADOS INICIAIS DE DEMONSTRAÇÃO
# =========================================================

VEICULO_PADRAO = {
    "marca": "Chevrolet",
    "modelo": "Onix",
    "ano": 2022,
    "combustivel": "Flex",
    "km": 48500,
    "uso": 1000,
}


PLANOS_PADRAO = [
    {
        "servico": "Troca de óleo e filtro",
        "ultima": 40000,
        "intervalo": 10000,
    },
    {
        "servico": "Filtro de ar",
        "ultima": 35000,
        "intervalo": 10000,
    },
    {
        "servico": "Alinhamento e balanceamento",
        "ultima": 42000,
        "intervalo": 10000,
    },
    {
        "servico": "Revisão dos freios",
        "ultima": 40000,
        "intervalo": 10000,
    },
    {
        "servico": "Bateria",
        "ultima": 30000,
        "intervalo": 30000,
    },
]


# =========================================================
# ESTADO DA SESSÃO
# =========================================================

if "veiculo" not in st.session_state:
    st.session_state.veiculo = VEICULO_PADRAO.copy()

if "planos" not in st.session_state:
    st.session_state.planos = [
        plano.copy()
        for plano in PLANOS_PADRAO
    ]

if "historico" not in st.session_state:
    st.session_state.historico = []

if "solicitacoes" not in st.session_state:
    st.session_state.solicitacoes = []

if "oficina" not in st.session_state:
    st.session_state.oficina = ""


# =========================================================
# FUNÇÕES DE MANUTENÇÃO
# =========================================================

def calcular_status_manutencao(item, km_atual):
    """
    Calcula o status da manutenção com base
    na quilometragem atual do veículo.
    """

    proxima_manutencao = (
        item["ultima"]
        + item["intervalo"]
    )

    saldo_km = (
        proxima_manutencao
        - km_atual
    )

    if saldo_km < 0:
        return (
            "Atrasado",
            saldo_km,
            proxima_manutencao,
            "🔴",
        )

    limite_alerta = max(
        1000,
        item["intervalo"] * 0.15,
    )

    if saldo_km <= limite_alerta:
        return (
            "Próximo",
            saldo_km,
            proxima_manutencao,
            "🟡",
        )

    return (
        "Em dia",
        saldo_km,
        proxima_manutencao,
        "🟢",
    )


# =========================================================
# FUNÇÕES DE LOCALIZAÇÃO
# =========================================================

def calcular_distancia_km(
    latitude_origem,
    longitude_origem,
    latitude_destino,
    longitude_destino,
):
    """
    Calcula a distância em linha reta entre duas coordenadas
    usando a fórmula de Haversine.
    """

    raio_terra_km = 6371

    latitude_origem_rad = math.radians(
        latitude_origem
    )

    latitude_destino_rad = math.radians(
        latitude_destino
    )

    diferenca_latitude = math.radians(
        latitude_destino
        - latitude_origem
    )

    diferenca_longitude = math.radians(
        longitude_destino
        - longitude_origem
    )

    calculo = (
        math.sin(
            diferenca_latitude / 2
        ) ** 2
        + math.cos(
            latitude_origem_rad
        )
        * math.cos(
            latitude_destino_rad
        )
        * math.sin(
            diferenca_longitude / 2
        ) ** 2
    )

    distancia_angular = (
        2
        * math.atan2(
            math.sqrt(calculo),
            math.sqrt(1 - calculo),
        )
    )

    return (
        raio_terra_km
        * distancia_angular
    )


def montar_endereco(tags):
    """
    Monta um endereço utilizando os dados
    disponíveis no OpenStreetMap.
    """

    endereco_completo = tags.get(
        "addr:full"
    )

    if endereco_completo:
        return endereco_completo

    partes = []

    rua = tags.get(
        "addr:street"
    )

    numero = tags.get(
        "addr:housenumber"
    )

    bairro = tags.get(
        "addr:suburb"
    )

    cidade = tags.get(
        "addr:city"
    )

    if rua:
        if numero:
            partes.append(
                f"{rua}, {numero}"
            )
        else:
            partes.append(rua)

    if bairro:
        partes.append(bairro)

    if cidade:
        partes.append(cidade)

    if partes:
        return " - ".join(partes)

    return "Endereço não informado"


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def buscar_estabelecimentos(
    latitude,
    longitude,
    raio_metros,
):
    """
    Busca oficinas, autopeças e lojas de pneus
    por meio da Overpass API do OpenStreetMap.
    """

    consulta = f"""
    [out:json][timeout:30];
    (
        nwr["shop"="car_repair"]
        (around:{raio_metros},{latitude},{longitude});

        nwr["craft"="car_repair"]
        (around:{raio_metros},{latitude},{longitude});

        nwr["shop"="car_parts"]
        (around:{raio_metros},{latitude},{longitude});

        nwr["shop"="tyres"]
        (around:{raio_metros},{latitude},{longitude});
    );
    out center tags;
    """

    servidores = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    dados = None
    ultimo_erro = None

    for servidor in servidores:
        try:
            resposta = requests.post(
                servidor,
                data={
                    "data": consulta
                },
                headers={
                    "User-Agent": (
                        "ManutCar-Academico/1.0"
                    )
                },
                timeout=50,
            )

            resposta.raise_for_status()

            dados = resposta.json()

            break

        except Exception as erro:
            ultimo_erro = erro

    if dados is None:
        raise RuntimeError(
            "A busca de estabelecimentos está "
            "temporariamente indisponível. "
            f"Detalhe técnico: {ultimo_erro}"
        )

    estabelecimentos = []
    registros_processados = set()

    for elemento in dados.get(
        "elements",
        [],
    ):
        tags = elemento.get(
            "tags",
            {},
        )

        latitude_estabelecimento = (
            elemento.get("lat")
        )

        longitude_estabelecimento = (
            elemento.get("lon")
        )

        if (
            latitude_estabelecimento is None
            or longitude_estabelecimento is None
        ):
            centro = elemento.get(
                "center",
                {},
            )

            latitude_estabelecimento = (
                centro.get("lat")
            )

            longitude_estabelecimento = (
                centro.get("lon")
            )

        if (
            latitude_estabelecimento is None
            or longitude_estabelecimento is None
        ):
            continue

        nome = tags.get(
            "name",
            "Estabelecimento sem nome",
        )

        chave_duplicidade = (
            nome,
            round(
                latitude_estabelecimento,
                5,
            ),
            round(
                longitude_estabelecimento,
                5,
            ),
        )

        if (
            chave_duplicidade
            in registros_processados
        ):
            continue

        registros_processados.add(
            chave_duplicidade
        )

        tipo_loja = tags.get(
            "shop"
        )

        tipo_servico = tags.get(
            "craft"
        )

        if (
            tipo_loja == "car_repair"
            or tipo_servico == "car_repair"
        ):
            categoria = (
                "Oficina mecânica"
            )

        elif tipo_loja == "car_parts":
            categoria = (
                "Loja de autopeças"
            )

        else:
            categoria = (
                "Loja de pneus"
            )

        distancia = calcular_distancia_km(
            latitude,
            longitude,
            latitude_estabelecimento,
            longitude_estabelecimento,
        )

        telefone = tags.get(
            "phone",
            tags.get(
                "contact:phone",
                "Não informado",
            ),
        )

        estabelecimento = {
            "Nome": nome,
            "Categoria": categoria,
            "Endereço": montar_endereco(
                tags
            ),
            "Latitude": (
                latitude_estabelecimento
            ),
            "Longitude": (
                longitude_estabelecimento
            ),
            "Distância": distancia,
            "Telefone": telefone,
        }

        estabelecimentos.append(
            estabelecimento
        )

    estabelecimentos.sort(
        key=lambda estabelecimento: (
            estabelecimento["Distância"]
        )
    )

    return estabelecimentos


def mostrar_titulo(
    titulo,
    subtitulo,
):
    """
    Mostra o título e a descrição de cada página.
    """

    st.title(titulo)
    st.caption(subtitulo)


# =========================================================
# MENU LATERAL
# =========================================================

with st.sidebar:
    st.markdown(
        """
        <div class="logo">
            🚗 ManutCar
        </div>

        <div class="sub">
            Manutenção preventiva sem complicação
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    pagina = st.radio(
        "Menu",
        [
            "Início",
            "Meu veículo",
            "Manutenções e alertas",
            "Histórico",
            "Encontrar oficinas",
            "Orçamentos e agendamentos",
            "Sobre",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.caption(
        "Protótipo acadêmico. "
        "Os dados são salvos somente durante a sessão."
    )


veiculo = st.session_state.veiculo


# =========================================================
# PÁGINA INICIAL
# =========================================================

if pagina == "Início":
    mostrar_titulo(
        "ManutCar",
        (
            "Organize o cuidado do veículo e encontre "
            "o próximo serviço em um só lugar."
        ),
    )

    coluna_veiculo, coluna_km, coluna_alertas = (
        st.columns(3)
    )

    coluna_veiculo.metric(
        "Veículo",
        (
            f"{veiculo['marca']} "
            f"{veiculo['modelo']}"
        ),
        str(veiculo["ano"]),
    )

    coluna_km.metric(
        "Quilometragem atual",
        (
            f"{veiculo['km']:,} km"
        ).replace(",", "."),
    )

    lista_alertas = [
        calcular_status_manutencao(
            item,
            veiculo["km"],
        )
        for item
        in st.session_state.planos
    ]

    quantidade_alertas = sum(
        resultado[0] != "Em dia"
        for resultado
        in lista_alertas
    )

    coluna_alertas.metric(
        "Alertas prioritários",
        quantidade_alertas,
    )

    st.subheader(
        "Próximos cuidados"
    )

    encontrou_alerta = False

    for item in st.session_state.planos:
        (
            situacao,
            saldo_km,
            proxima_manutencao,
            icone,
        ) = calcular_status_manutencao(
            item,
            veiculo["km"],
        )

        if situacao != "Em dia":
            encontrou_alerta = True

            if saldo_km < 0:
                mensagem = (
                    "Prazo ultrapassado em "
                    f"{abs(saldo_km):,} km"
                )
            else:
                mensagem = (
                    "Faltam aproximadamente "
                    f"{saldo_km:,} km"
                )

            mensagem = mensagem.replace(
                ",",
                ".",
            )

            st.markdown(
                f"""
                <div class="card">
                    <b>
                        {icone} {item["servico"]}
                    </b>
                    <br>
                    {mensagem}
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not encontrou_alerta:
        st.success(
            "Todas as manutenções cadastradas "
            "estão dentro do prazo estimado."
        )

    st.info(
        "Os intervalos deste protótipo são demonstrativos. "
        "Consulte o manual do fabricante e um profissional "
        "qualificado antes de realizar uma manutenção."
    )


# =========================================================
# PÁGINA MEU VEÍCULO
# =========================================================

elif pagina == "Meu veículo":
    mostrar_titulo(
        "Meu veículo",
        (
            "Atualize os dados utilizados "
            "nos alertas de manutenção."
        ),
    )

    with st.form(
        "formulario_veiculo"
    ):
        coluna_marca, coluna_modelo, coluna_ano = (
            st.columns(3)
        )

        marca = coluna_marca.text_input(
            "Marca",
            veiculo["marca"],
        )

        modelo = coluna_modelo.text_input(
            "Modelo",
            veiculo["modelo"],
        )

        ano = coluna_ano.number_input(
            "Ano",
            min_value=1980,
            max_value=2030,
            value=veiculo["ano"],
        )

        (
            coluna_combustivel,
            coluna_quilometragem,
            coluna_uso,
        ) = st.columns(3)

        opcoes_combustivel = [
            "Flex",
            "Gasolina",
            "Etanol",
            "Diesel",
            "Elétrico",
            "Híbrido",
        ]

        combustivel = (
            coluna_combustivel.selectbox(
                "Combustível",
                opcoes_combustivel,
                index=opcoes_combustivel.index(
                    veiculo["combustivel"]
                ),
            )
        )

        quilometragem = (
            coluna_quilometragem.number_input(
                "Quilometragem atual",
                min_value=0,
                max_value=1000000,
                value=veiculo["km"],
                step=100,
            )
        )

        uso_mensal = coluna_uso.number_input(
            "Uso médio mensal em quilômetros",
            min_value=0,
            max_value=10000,
            value=veiculo["uso"],
            step=100,
        )

        salvar_veiculo = (
            st.form_submit_button(
                "Salvar veículo",
                type="primary",
            )
        )

        if salvar_veiculo:
            st.session_state.veiculo = {
                "marca": marca,
                "modelo": modelo,
                "ano": int(ano),
                "combustivel": combustivel,
                "km": int(quilometragem),
                "uso": int(uso_mensal),
            }

            st.success(
                "Veículo atualizado com sucesso."
            )


# =========================================================
# PÁGINA MANUTENÇÕES E ALERTAS
# =========================================================

elif pagina == "Manutenções e alertas":
    mostrar_titulo(
        "Manutenções e alertas",
        (
            "Acompanhe os prazos estimados "
            "por quilometragem."
        ),
    )

    linhas_manutencao = []

    for item in st.session_state.planos:
        (
            situacao,
            saldo_km,
            proxima_manutencao,
            icone,
        ) = calcular_status_manutencao(
            item,
            veiculo["km"],
        )

        linhas_manutencao.append(
            {
                "Status": (
                    f"{icone} {situacao}"
                ),
                "Serviço": (
                    item["servico"]
                ),
                "Última realização (km)": (
                    item["ultima"]
                ),
                "Próxima previsão (km)": (
                    proxima_manutencao
                ),
                "Saldo (km)": saldo_km,
            }
        )

    tabela_manutencoes = pd.DataFrame(
        linhas_manutencao
    )

    st.dataframe(
        tabela_manutencoes,
        use_container_width=True,
        hide_index=True,
    )

    with st.expander(
        "Adicionar plano de manutenção"
    ):
        with st.form(
            "formulario_plano"
        ):
            novo_servico = st.text_input(
                "Serviço"
            )

            (
                coluna_ultima_km,
                coluna_intervalo,
            ) = st.columns(2)

            ultima_realizacao = (
                coluna_ultima_km.number_input(
                    "Última realização em quilômetros",
                    min_value=0,
                    max_value=1000000,
                    value=veiculo["km"],
                )
            )

            intervalo = (
                coluna_intervalo.number_input(
                    "Intervalo da manutenção em quilômetros",
                    min_value=500,
                    max_value=100000,
                    value=10000,
                    step=500,
                )
            )

            adicionar_plano = (
                st.form_submit_button(
                    "Adicionar plano"
                )
            )

            if adicionar_plano:
                if novo_servico.strip():
                    st.session_state.planos.append(
                        {
                            "servico": (
                                novo_servico
                            ),
                            "ultima": int(
                                ultima_realizacao
                            ),
                            "intervalo": int(
                                intervalo
                            ),
                        }
                    )

                    st.success(
                        "Plano de manutenção adicionado."
                    )

                else:
                    st.warning(
                        "Informe o nome do serviço."
                    )


# =========================================================
# PÁGINA HISTÓRICO
# =========================================================

elif pagina == "Histórico":
    mostrar_titulo(
        "Histórico de manutenção",
        (
            "Centralize os serviços realizados "
            "no veículo."
        ),
    )

    with st.form(
        "formulario_historico"
    ):
        (
            coluna_data,
            coluna_km,
            coluna_valor,
        ) = st.columns(3)

        data_servico = (
            coluna_data.date_input(
                "Data",
                value=date.today(),
            )
        )

        quilometragem_servico = (
            coluna_km.number_input(
                "Quilometragem",
                min_value=0,
                max_value=1000000,
                value=veiculo["km"],
            )
        )

        valor_servico = (
            coluna_valor.number_input(
                "Valor do serviço em reais",
                min_value=0.0,
                max_value=100000.0,
                value=0.0,
                step=10.0,
            )
        )

        opcoes_servicos = [
            item["servico"]
            for item
            in st.session_state.planos
        ]

        opcoes_servicos.append(
            "Outro"
        )

        servico_realizado = st.selectbox(
            "Serviço realizado",
            opcoes_servicos,
        )

        oficina_historico = st.text_input(
            "Oficina"
        )

        observacoes_historico = (
            st.text_area(
                "Observações"
            )
        )

        registrar_historico = (
            st.form_submit_button(
                "Registrar serviço",
                type="primary",
            )
        )

        if registrar_historico:
            novo_registro = {
                "Data": str(
                    data_servico
                ),
                "Quilometragem": int(
                    quilometragem_servico
                ),
                "Serviço": (
                    servico_realizado
                ),
                "Oficina": (
                    oficina_historico
                    if oficina_historico
                    else "Não informada"
                ),
                "Valor (R$)": (
                    valor_servico
                ),
                "Observações": (
                    observacoes_historico
                ),
            }

            st.session_state.historico.append(
                novo_registro
            )

            st.success(
                "Serviço registrado no histórico "
                "desta sessão."
            )

    if st.session_state.historico:
        tabela_historico = pd.DataFrame(
            st.session_state.historico
        )

        st.dataframe(
            tabela_historico,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info(
            "Nenhum serviço foi registrado "
            "nesta sessão."
        )


# =========================================================
# PÁGINA ENCONTRAR OFICINAS
# =========================================================

elif pagina == "Encontrar oficinas":
    mostrar_titulo(
        "Encontrar oficinas",
        (
            "Consulte estabelecimentos próximos "
            "usando a localização do dispositivo."
        ),
    )

    (
        coluna_raio,
        coluna_categoria,
        coluna_limite,
    ) = st.columns(3)

    raio_km = coluna_raio.select_slider(
        "Raio de busca",
        options=[
            1,
            2,
            3,
            5,
            10,
            15,
        ],
        value=5,
        format_func=lambda valor: (
            f"{valor} km"
        ),
    )

    categoria_selecionada = (
        coluna_categoria.selectbox(
            "Categoria",
            [
                "Todos",
                "Oficina mecânica",
                "Loja de autopeças",
                "Loja de pneus",
            ],
        )
    )

    limite_resultados = (
        coluna_limite.slider(
            "Quantidade de resultados",
            min_value=5,
            max_value=40,
            value=20,
            step=5,
        )
    )

    st.write(
        "Clique no botão abaixo para usar "
        "a localização atual do dispositivo."
    )

    localizacao = get_geolocation()

    latitude = None
    longitude = None
    erro_localizacao = None

    if localizacao:
        if "coords" in localizacao:
            coordenadas = (
                localizacao["coords"]
            )

            latitude = coordenadas.get(
                "latitude"
            )

            longitude = coordenadas.get(
                "longitude"
            )

        elif "error" in localizacao:
            erro_localizacao = (
                localizacao["error"]
            )

    if erro_localizacao:
        st.error(
            "Não foi possível obter a localização. "
            "Verifique as permissões do navegador "
            "e os serviços de localização do dispositivo."
        )

        st.json(
            erro_localizacao
        )

    if (
        latitude is None
        or longitude is None
    ):
        st.info(
            "Clique no botão de localização e permita "
            "o acesso quando o navegador solicitar."
        )

    else:
        latitude = float(latitude)
        longitude = float(longitude)

        st.success(
            "Localização obtida com sucesso."
        )

        try:
            with st.spinner(
                "Buscando estabelecimentos próximos..."
            ):
                resultados = buscar_estabelecimentos(
                    latitude,
                    longitude,
                    raio_km * 1000,
                )

            if (
                categoria_selecionada
                != "Todos"
            ):
                resultados = [
                    estabelecimento
                    for estabelecimento
                    in resultados
                    if estabelecimento[
                        "Categoria"
                    ]
                    == categoria_selecionada
                ]

            resultados = resultados[
                :limite_resultados
            ]

            if not resultados:
                st.warning(
                    "Nenhum estabelecimento foi encontrado. "
                    "Selecione a categoria Todos ou aumente "
                    "o raio de busca."
                )

            else:
                st.success(
                    f"{len(resultados)} estabelecimento(s) "
                    "encontrado(s)."
                )

                mapa = folium.Map(
                    location=[
                        latitude,
                        longitude,
                    ],
                    zoom_start=14,
                )

                folium.CircleMarker(
                    location=[
                        latitude,
                        longitude,
                    ],
                    radius=9,
                    color="#075A5A",
                    fill=True,
                    fill_color="#075A5A",
                    tooltip="Você está aqui",
                ).add_to(mapa)

                for estabelecimento in resultados:
                    popup = (
                        f"{estabelecimento['Nome']}"
                        "<br>"
                        f"{estabelecimento['Categoria']}"
                        "<br>"
                        f"{estabelecimento['Distância']:.2f} km"
                    )

                    folium.Marker(
                        location=[
                            estabelecimento[
                                "Latitude"
                            ],
                            estabelecimento[
                                "Longitude"
                            ],
                        ],
                        tooltip=estabelecimento[
                            "Nome"
                        ],
                        popup=popup,
                    ).add_to(mapa)

                st_folium(
                    mapa,
                    width=None,
                    height=480,
                    returned_objects=[],
                )

                st.subheader(
                    "Estabelecimentos encontrados"
                )

                for (
                    posicao,
                    estabelecimento,
                ) in enumerate(
                    resultados,
                    start=1,
                ):
                    titulo_expansor = (
                        f"{posicao}. "
                        f"{estabelecimento['Nome']} "
                        "• "
                        f"{estabelecimento['Distância']:.2f} km"
                    )

                    with st.expander(
                        titulo_expansor
                    ):
                        st.write(
                            "**Categoria:** "
                            f"{estabelecimento['Categoria']}"
                        )

                        st.write(
                            "**Endereço:** "
                            f"{estabelecimento['Endereço']}"
                        )

                        st.write(
                            "**Telefone:** "
                            f"{estabelecimento['Telefone']}"
                        )

                        link_rota = (
                            "https://www.google.com/maps/dir/"
                            "?api=1"
                            "&destination="
                            f"{estabelecimento['Latitude']},"
                            f"{estabelecimento['Longitude']}"
                        )

                        (
                            coluna_rota,
                            coluna_orcamento,
                        ) = st.columns(2)

                        coluna_rota.link_button(
                            "Abrir rota",
                            link_rota,
                            use_container_width=True,
                        )

                        selecionar_oficina = (
                            coluna_orcamento.button(
                                "Selecionar para orçamento",
                                key=(
                                    "oficina_"
                                    f"{posicao}"
                                ),
                                use_container_width=True,
                            )
                        )

                        if selecionar_oficina:
                            st.session_state.oficina = (
                                estabelecimento[
                                    "Nome"
                                ]
                            )

                            st.success(
                                "Oficina selecionada. "
                                "Abra a página Orçamentos "
                                "e agendamentos."
                            )

        except Exception as erro:
            st.error(
                "Não foi possível concluir a busca."
            )

            st.code(
                str(erro)
            )

    st.caption(
        "Dados dos estabelecimentos: "
        "© OpenStreetMap contributors. "
        "Os estabelecimentos apresentados não são "
        "parceiros confirmados do ManutCar."
    )


# =========================================================
# PÁGINA ORÇAMENTOS E AGENDAMENTOS
# =========================================================

elif pagina == "Orçamentos e agendamentos":
    mostrar_titulo(
        "Orçamentos e agendamentos",
        (
            "Simule a conexão entre uma necessidade "
            "de manutenção e uma oficina."
        ),
    )

    with st.form(
        "formulario_solicitacao"
    ):
        oficina_solicitacao = st.text_input(
            "Oficina",
            value=st.session_state.oficina,
        )

        servicos_disponiveis = [
            item["servico"]
            for item
            in st.session_state.planos
        ]

        servicos_disponiveis.extend(
            [
                "Diagnóstico",
                "Outro",
            ]
        )

        servico_solicitado = st.selectbox(
            "Serviço solicitado",
            servicos_disponiveis,
        )

        tipo_solicitacao = st.radio(
            "Tipo de solicitação",
            [
                "Orçamento",
                "Agendamento",
            ],
            horizontal=True,
        )

        data_desejada = st.date_input(
            "Data desejada",
            value=date.today(),
        )

        periodo = st.selectbox(
            "Período desejado",
            [
                "Manhã",
                "Tarde",
                "Indiferente",
            ],
        )

        contato = st.text_input(
            "Contato para retorno demonstrativo"
        )

        detalhes = st.text_area(
            "Descrição ou observações"
        )

        enviar_solicitacao = (
            st.form_submit_button(
                "Enviar solicitação",
                type="primary",
            )
        )

        if enviar_solicitacao:
            nova_solicitacao = {
                "Tipo": tipo_solicitacao,
                "Oficina": (
                    oficina_solicitacao
                    if oficina_solicitacao
                    else "Não selecionada"
                ),
                "Serviço": (
                    servico_solicitado
                ),
                "Data": str(
                    data_desejada
                ),
                "Período": periodo,
                "Status": "Demonstrativo",
            }

            st.session_state.solicitacoes.append(
                nova_solicitacao
            )

            st.success(
                "Solicitação registrada para demonstração. "
                "Nenhuma oficina real recebeu os dados."
            )

    if st.session_state.solicitacoes:
        tabela_solicitacoes = pd.DataFrame(
            st.session_state.solicitacoes
        )

        st.dataframe(
            tabela_solicitacoes,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info(
            "Nenhuma solicitação foi registrada "
            "nesta sessão."
        )


# =========================================================
# PÁGINA SOBRE
# =========================================================

else:
    mostrar_titulo(
        "Sobre o ManutCar",
        "Manutenção preventiva sem complicação.",
    )

    st.markdown(
        """
        ### Proposta

        O ManutCar reúne cadastro do veículo, quilometragem,
        histórico, alertas de manutenção, localização de
        oficinas, solicitação de orçamento e agendamento em
        uma única jornada.

        ### Jornada do usuário

        1. Cadastrar o veículo;
        2. Informar a quilometragem atual;
        3. Receber alertas de manutenção;
        4. Consultar estabelecimentos próximos;
        5. Solicitar orçamento ou agendamento;
        6. Registrar o serviço no histórico.

        ### Aviso

        Este é um protótipo acadêmico. Os alertas, intervalos,
        convênios, disponibilidade e solicitações apresentados
        são demonstrativos. Recomendações reais devem considerar
        o manual do fabricante e a avaliação de um profissional
        qualificado.
        """
    )


# =========================================================
# RODAPÉ
# =========================================================

st.divider()

st.caption(
    "ManutCar • Protótipo acadêmico • "
    "Dados de oficinas: © OpenStreetMap contributors"
)