import math
import random

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
    page_title="AutoPerto",
    page_icon="🚗",
    layout="wide",
)


# =========================================================
# FUNÇÕES
# =========================================================

def calcular_distancia_km(lat1, lon1, lat2, lon2):
    """
    Calcula a distância em linha reta entre duas coordenadas
    usando a fórmula de Haversine.
    """

    raio_terra_km = 6371

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    diferenca_latitude = lat2_rad - lat1_rad
    diferenca_longitude = lon2_rad - lon1_rad

    a = (
        math.sin(diferenca_latitude / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(diferenca_longitude / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return raio_terra_km * c


def montar_endereco(tags):
    """
    Monta o endereço usando os campos disponíveis
    nos dados do OpenStreetMap.
    """

    endereco_completo = tags.get("addr:full")

    if endereco_completo:
        return endereco_completo

    partes = []

    rua = tags.get("addr:street")
    numero = tags.get("addr:housenumber")
    bairro = tags.get("addr:suburb")
    cidade = tags.get("addr:city")

    if rua:
        if numero:
            partes.append(f"{rua}, {numero}")
        else:
            partes.append(rua)

    if bairro:
        partes.append(bairro)

    if cidade:
        partes.append(cidade)

    if partes:
        return " - ".join(partes)

    return "Endereço não informado"


def identificar_categoria(tags):
    """
    Identifica a categoria do estabelecimento utilizando
    as classificações do OpenStreetMap.
    """

    tipo_loja = tags.get("shop", "")
    tipo_servico = tags.get("craft", "")

    if tipo_loja == "car_repair" or tipo_servico == "car_repair":
        return "Oficina mecânica"

    if tipo_loja == "car_parts":
        return "Loja de autopeças"

    if tipo_loja == "tyres":
        return "Loja de pneus"

    return "Serviço automotivo"


def criar_desconto_simulado(id_estabelecimento):
    """
    Cria um desconto demonstrativo fixo para cada estabelecimento.
    """

    gerador = random.Random(str(id_estabelecimento))

    return gerador.choice([5, 10, 15, 20])


@st.cache_data(ttl=300, show_spinner=False)
def buscar_estabelecimentos(latitude, longitude, raio_metros):
    """
    Consulta oficinas, lojas de autopeças e lojas de pneus
    pela Overpass API do OpenStreetMap.

    O resultado permanece em cache durante 5 minutos.
    """

    consulta = f"""
    [out:json][timeout:30];
    (
        node["shop"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});
        way["shop"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});
        relation["shop"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});

        node["craft"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});
        way["craft"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});
        relation["craft"="car_repair"]
            (around:{raio_metros},{latitude},{longitude});

        node["shop"="car_parts"]
            (around:{raio_metros},{latitude},{longitude});
        way["shop"="car_parts"]
            (around:{raio_metros},{latitude},{longitude});
        relation["shop"="car_parts"]
            (around:{raio_metros},{latitude},{longitude});

        node["shop"="tyres"]
            (around:{raio_metros},{latitude},{longitude});
        way["shop"="tyres"]
            (around:{raio_metros},{latitude},{longitude});
        relation["shop"="tyres"]
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
                data={"data": consulta},
                headers={
                    "User-Agent": (
                        "AutoPerto-Projeto-Academico/1.0"
                    )
                },
                timeout=50,
            )

            resposta.raise_for_status()
            dados = resposta.json()
            break

        except (
            requests.RequestException,
            ValueError,
        ) as erro:
            ultimo_erro = erro

    if dados is None:
        raise RuntimeError(
            "Não foi possível consultar os estabelecimentos. "
            f"Detalhe técnico: {ultimo_erro}"
        )

    estabelecimentos = []
    registros_processados = set()

    for elemento in dados.get("elements", []):
        tags = elemento.get("tags", {})

        latitude_estabelecimento = elemento.get("lat")
        longitude_estabelecimento = elemento.get("lon")

        if (
            latitude_estabelecimento is None
            or longitude_estabelecimento is None
        ):
            centro = elemento.get("center", {})

            latitude_estabelecimento = centro.get("lat")
            longitude_estabelecimento = centro.get("lon")

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
            nome.lower().strip(),
            round(float(latitude_estabelecimento), 5),
            round(float(longitude_estabelecimento), 5),
        )

        if chave_duplicidade in registros_processados:
            continue

        registros_processados.add(chave_duplicidade)

        distancia_km = calcular_distancia_km(
            float(latitude),
            float(longitude),
            float(latitude_estabelecimento),
            float(longitude_estabelecimento),
        )

        desconto_simulado = criar_desconto_simulado(
            elemento.get("id")
        )

        estabelecimento = {
            "Nome": nome,
            "Categoria": identificar_categoria(tags),
            "Endereco": montar_endereco(tags),
            "Telefone": tags.get(
                "phone",
                tags.get(
                    "contact:phone",
                    "Não informado",
                ),
            ),
            "Site": tags.get(
                "website",
                tags.get(
                    "contact:website",
                    "",
                ),
            ),
            "Horario": tags.get(
                "opening_hours",
                "Não informado",
            ),
            "Latitude": float(latitude_estabelecimento),
            "Longitude": float(longitude_estabelecimento),
            "Distancia_km": distancia_km,
            "Desconto": desconto_simulado,
        }

        estabelecimentos.append(estabelecimento)

    estabelecimentos.sort(
        key=lambda item: item["Distancia_km"]
    )

    return estabelecimentos


def criar_link_rota(latitude_destino, longitude_destino):
    """
    Cria um link para abrir a rota no Google Maps.
    """

    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={latitude_destino},{longitude_destino}"
    )


def criar_mapa(
    latitude_usuario,
    longitude_usuario,
    estabelecimentos,
):
    """
    Cria o mapa com a localização do usuário
    e os estabelecimentos encontrados.
    """

    mapa = folium.Map(
        location=[
            latitude_usuario,
            longitude_usuario,
        ],
        zoom_start=14,
        control_scale=True,
    )

    folium.CircleMarker(
        location=[
            latitude_usuario,
            longitude_usuario,
        ],
        radius=9,
        color="#0057B8",
        fill=True,
        fill_color="#009FE3",
        fill_opacity=1,
        tooltip="Você está aqui",
        popup="Sua localização atual",
    ).add_to(mapa)

    for estabelecimento in estabelecimentos:
        categoria = estabelecimento["Categoria"]

        if categoria == "Oficina mecânica":
            cor = "red"
            icone = "wrench"

        elif categoria == "Loja de autopeças":
            cor = "green"
            icone = "shopping-cart"

        elif categoria == "Loja de pneus":
            cor = "orange"
            icone = "car"

        else:
            cor = "gray"
            icone = "info-sign"

        link_rota = criar_link_rota(
            estabelecimento["Latitude"],
            estabelecimento["Longitude"],
        )

        popup = f"""
        <div style="width: 240px;">
            <strong>{estabelecimento["Nome"]}</strong>
            <br>
            {estabelecimento["Categoria"]}
            <br>
            Distância:
            {estabelecimento["Distancia_km"]:.2f} km
            <br>
            Desconto demonstrativo:
            {estabelecimento["Desconto"]}%
            <br><br>
            <a href="{link_rota}" target="_blank">
                Abrir rota
            </a>
        </div>
        """

        folium.Marker(
            location=[
                estabelecimento["Latitude"],
                estabelecimento["Longitude"],
            ],
            tooltip=estabelecimento["Nome"],
            popup=folium.Popup(
                popup,
                max_width=280,
            ),
            icon=folium.Icon(
                color=cor,
                icon=icone,
                prefix="fa",
            ),
        ).add_to(mapa)

    return mapa


# =========================================================
# CABEÇALHO
# =========================================================

st.title("🚗 AutoPerto")

st.write(
    "Encontre oficinas, lojas de autopeças e lojas de pneus "
    "próximas da sua localização."
)

st.warning(
    "Este é um protótipo acadêmico. Os estabelecimentos são "
    "obtidos a partir de dados públicos. Os descontos e convênios "
    "apresentados são apenas demonstrativos."
)


# =========================================================
# BARRA LATERAL
# =========================================================

with st.sidebar:
    st.header("Configurações da busca")

    raio_km = st.select_slider(
        "Raio de busca",
        options=[1, 2, 3, 5, 10, 15],
        value=5,
        format_func=lambda valor: f"{valor} km",
    )

    categoria_escolhida = st.selectbox(
        "Tipo de estabelecimento",
        options=[
            "Todos",
            "Oficina mecânica",
            "Loja de autopeças",
            "Loja de pneus",
        ],
    )

    limite_resultados = st.slider(
        "Quantidade máxima de resultados",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
    )

    st.caption(
        "A localização é utilizada somente para realizar "
        "a busca de estabelecimentos próximos."
    )


# =========================================================
# LOCALIZAÇÃO
# =========================================================

st.subheader("1. Informe sua localização")

st.write(
    "Clique no botão abaixo e autorize o navegador a acessar "
    "a localização do dispositivo."
)

localizacao = get_geolocation()

latitude = None
longitude = None
precisao = None
erro_localizacao = None

if localizacao:
    if "error" in localizacao:
        erro_localizacao = localizacao["error"]

    elif "coords" in localizacao:
        coordenadas = localizacao["coords"]

        latitude = coordenadas.get("latitude")
        longitude = coordenadas.get("longitude")
        precisao = coordenadas.get("accuracy")


# =========================================================
# TRATAMENTO DOS ERROS DE LOCALIZAÇÃO
# =========================================================

if erro_localizacao:
    codigo_erro = erro_localizacao.get("code")

    mensagem_erro = erro_localizacao.get(
        "message",
        "Não foi possível obter a localização.",
    )

    if codigo_erro == 1:
        st.error(
            "A permissão de localização foi negada. "
            "Libere a localização nas configurações do navegador "
            "e atualize a página."
        )

    elif codigo_erro == 2:
        st.error(
            "A localização está indisponível. Ative os serviços "
            "de localização do Windows e tente novamente."
        )

    elif codigo_erro == 3:
        st.error(
            "A consulta da localização demorou demais. "
            "Clique novamente no botão de localização."
        )

    else:
        st.error(
            f"Erro ao obter a localização: {mensagem_erro}"
        )


# =========================================================
# RESULTADOS
# =========================================================

if latitude is not None and longitude is not None:
    latitude = float(latitude)
    longitude = float(longitude)

    st.success("Localização obtida com sucesso.")

    coluna_latitude, coluna_longitude, coluna_precisao = (
        st.columns(3)
    )

    with coluna_latitude:
        st.metric(
            "Latitude",
            f"{latitude:.6f}",
        )

    with coluna_longitude:
        st.metric(
            "Longitude",
            f"{longitude:.6f}",
        )

    with coluna_precisao:
        if precisao is not None:
            st.metric(
                "Precisão aproximada",
                f"{float(precisao):.0f} metros",
            )
        else:
            st.metric(
                "Precisão aproximada",
                "Não informada",
            )

    st.subheader("2. Estabelecimentos próximos")

    try:
        with st.spinner(
            "Buscando estabelecimentos próximos..."
        ):
            resultados = buscar_estabelecimentos(
                latitude=latitude,
                longitude=longitude,
                raio_metros=raio_km * 1000,
            )

        if categoria_escolhida != "Todos":
            resultados = [
                estabelecimento
                for estabelecimento in resultados
                if estabelecimento["Categoria"]
                == categoria_escolhida
            ]

        resultados = resultados[:limite_resultados]

        if not resultados:
            st.info(
                "Nenhum estabelecimento foi encontrado com os "
                "filtros selecionados. Selecione 'Todos' ou aumente "
                "o raio de busca."
            )

        else:
            st.success(
                f"{len(resultados)} estabelecimento(s) encontrado(s)."
            )

            mapa = criar_mapa(
                latitude_usuario=latitude,
                longitude_usuario=longitude,
                estabelecimentos=resultados,
            )

            st_folium(
                mapa,
                width=None,
                height=520,
                returned_objects=[],
            )

            st.subheader("3. Lista de estabelecimentos")

            for posicao, estabelecimento in enumerate(
                resultados,
                start=1,
            ):
                titulo = (
                    f"{posicao}. "
                    f"{estabelecimento['Nome']} "
                    f"• "
                    f"{estabelecimento['Distancia_km']:.2f} km"
                )

                with st.expander(titulo):
                    coluna_informacoes, coluna_beneficio = (
                        st.columns([2, 1])
                    )

                    with coluna_informacoes:
                        st.write(
                            "**Categoria:** "
                            f"{estabelecimento['Categoria']}"
                        )

                        st.write(
                            "**Endereço:** "
                            f"{estabelecimento['Endereco']}"
                        )

                        st.write(
                            "**Telefone:** "
                            f"{estabelecimento['Telefone']}"
                        )

                        st.write(
                            "**Horário:** "
                            f"{estabelecimento['Horario']}"
                        )

                        if estabelecimento["Site"]:
                            st.markdown(
                                "[Acessar site do estabelecimento]"
                                f"({estabelecimento['Site']})"
                            )

                    with coluna_beneficio:
                        st.metric(
                            "Desconto demonstrativo",
                            f"{estabelecimento['Desconto']}%",
                        )

                        link_rota = criar_link_rota(
                            estabelecimento["Latitude"],
                            estabelecimento["Longitude"],
                        )

                        st.link_button(
                            "🧭 Abrir rota",
                            link_rota,
                            use_container_width=True,
                        )

                        chave_botao = (
                            f"agendamento_{posicao}_"
                            f"{estabelecimento['Latitude']}_"
                            f"{estabelecimento['Longitude']}"
                        )

                        if st.button(
                            "Solicitar agendamento",
                            key=chave_botao,
                            use_container_width=True,
                        ):
                            st.success(
                                "Solicitação registrada apenas "
                                "para demonstração."
                            )

            tabela = pd.DataFrame(resultados)

            tabela_exibicao = tabela[
                [
                    "Nome",
                    "Categoria",
                    "Endereco",
                    "Distancia_km",
                    "Desconto",
                ]
            ].copy()

            tabela_exibicao["Distancia_km"] = (
                tabela_exibicao["Distancia_km"].round(2)
            )

            tabela_exibicao = tabela_exibicao.rename(
                columns={
                    "Endereco": "Endereço",
                    "Distancia_km": "Distância (km)",
                    "Desconto": "Desconto demonstrativo (%)",
                }
            )

            with st.expander(
                "Ver resultados em formato de tabela"
            ):
                st.dataframe(
                    tabela_exibicao,
                    use_container_width=True,
                    hide_index=True,
                )

    except Exception as erro:
        st.error(
            "Não foi possível buscar os estabelecimentos "
            "neste momento."
        )

        st.code(str(erro))

        st.info(
            "A Overpass API é um serviço público e pode ficar "
            "temporariamente indisponível. Aguarde alguns minutos "
            "e tente novamente."
        )

else:
    if not erro_localizacao:
        st.info(
            "Clique no botão de localização e aguarde alguns "
            "segundos. Se o navegador solicitar autorização, "
            "selecione 'Permitir'."
        )


# =========================================================
# RODAPÉ
# =========================================================

st.divider()

st.caption(
    "Dados dos estabelecimentos: © OpenStreetMap contributors. "
    "Projeto acadêmico sem vínculo comercial com os estabelecimentos."
)