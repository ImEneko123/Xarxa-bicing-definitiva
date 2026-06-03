import streamlit as st
import pickle
import pandas as pd
import datetime
import requests
import io
@st.cache_resource
def carregar_model_des_de_dropbox():
    url = "https://www.dropbox.com/scl/fi/a5uqlxapxfh7wisbsw5wc/model_bicing_bosc_definitiu.pkl?rlkey=ispa6kkcscw9ukxvdt8tpjcf0&st=7eefesuu&dl=1"
    
    # Dropbox ens dona el fitxer directe sense pantalles de virus!
    resposta = requests.get(url)
    
    fitxer_memoria = io.BytesIO(resposta.content)
    return pickle.load(fitxer_memoria)

# Carreguem el model
model_bicing_bosc_definitiu = carregar_model_des_de_dropbox()
# Graella per als minuts d'antelació
minuts_futur = st.text_input("Minuts per arribar:")

@st.cache_data
def carregar_estacions():
    return pd.read_csv('estacions_bicing.csv')

df_estacions = carregar_estacions()
# Combinem l'id real i el nom del carrer
st.subheader("Selecció d'Estació")
df_estacions['opcio_visual'] = "Estació " + df_estacions['id'].astype(str) + " - " + df_estacions['streetName']

llista_opcions = sorted(df_estacions['opcio_visual'].unique())

# El desplegable ara té index=None perquè surti BUIT per defecte
estacio_seleccionada = st.selectbox(
    "Busca per carrer o número d'estació:",
    llista_opcions,
    index=None,
    placeholder="Escriu per buscar...",
)

# ATENCIÓ: Si no ha triat res encara, mostrem un avís i ATUREM l'execució de la web
if not estacio_seleccionada:
    st.info("Busca i selecciona una estació de Bicing per començar.")
    st.stop()

# Si ja ha triat una estació, el codi continua i busquem les coordenades
fila_estacio = df_estacions[df_estacions['opcio_visual'] == estacio_seleccionada].iloc[0]
lat = fila_estacio['latitude']
lon = fila_estacio['longitude']

# Comprovem si la capsa està buida. Si ho està, posem un 0 per defecte
if not minuts_futur:
    minuts_futur = 0

# 1. Calculem l'hora ACTUAL a Barcelona (el teu codi original era perfecte)
ara = pd.Timestamp.now(tz='Europe/Madrid')

# 2. Calculem el moment FUTUR sumant-hi els minuts
moment_futur = ara + pd.Timedelta(minutes=int(minuts_futur))

# 3. ⚠️ AQUÍ ESTÀ LA CLAU: Actualitzem les variables per a la IA amb el temps FUTUR
hora_decimal = moment_futur.hour + (moment_futur.minute / 60.0)
dia_setmana = moment_futur.weekday() # 0=Dilluns

# A partir d'aquí, ja pots deixar l'st.info que tenies a la línia 69:
# st.info(f"Predicció per a: **{moment_futur.strftime('%H:%M')}**...")



st.info(f"Predicció per a: **{moment_futur.strftime('%H:%M')}** ({moment_futur.strftime('%A')})")

import requests

def obtenir_clima_futur(lat, lon, hora_seleccionada):
    # 🔑 Posa aquí la clau que has copiat de WeatherAPI
    api_key = "c9dc5c80c2fb4a5195b153641260306" 
    
    # URL de previsió per a les coordenades triades
    url = f"http://api.weatherapi.com/v1/forecast.json?key={api_key}&q={lat},{lon}&days=1&aqi=no&alerts=no"
    
    try:
        resposta = requests.get(url).json()
        
        # L'API ens torna una llista de 24 hores per a avui. Busquem la posició de l'hora triada:
        index_hora = int(hora_seleccionada)
        dades_hora = resposta['forecast']['forecastday'][0]['hour'][index_hora]
        
        # Extraiem la temperatura real d'aquella hora
        temp_actual = dades_hora['temp_c']
        
        # WeatherAPI ja ens diu directament si plourà en aquella hora (1 = Sí, 0 = No)
        pluja_activa = dades_hora['will_it_rain']
        
        return temp_actual, pluja_activa

    except Exception as e:
        st.error(f"Error en connectar amb WeatherAPI: {e}")
        return 18.0, 0  # Pla B d'emergència si falla internet
   
# Cridem a la nova funció passant-li la latitud, longitud i l'hora de l'slider
temp_actual, pluja_actual = obtenir_clima_futur(lat, lon, hora_decimal)

# (Opcional) Mostrem a la web el clima detectat per a aquella hora
st.write(f"**Clima previst per a aquesta hora:** {temp_actual}°C i {'amb pluja' if pluja_actual == 1 else 'sense pluja'}")

#Saber si esta tancada o oberta
def obtenir_estat_estacio(id_estacio):
    url = "https://api.bsmsa.eu/ext/api/bsm/gbfs/v2/en/station_status"
    resposta = requests.get(url)
    
    # Comprovem que la petició ha anat bé
    if resposta.status_code == 200:
        dades = resposta.json()
        estacions = dades['data']['stations']
        
        # Busquem la nostra estació a la llista
        for estacio in estacions:
            if int(estacio['station_id']) == int(id_estacio):
                estat_text = estacio['status'] # Aquí dirà 'IN_SERVICE' o 'CLOSED'
                
                # Ho convertim a números per la nostra IA (1 = Obert, 0 = Tancat)
                if estat_text == 'IN_SERVICE':
                    return 1
                else:
                    return 0
                    
    # Si alguna cosa falla amb l'internet, assumim que està oberta (1) per no trencar l'app
    return 1
id_seleccionat = df_estacions[df_estacions['opcio_visual'] == estacio_seleccionada]['id'].values[0]
status_actual = obtenir_estat_estacio(id_seleccionat)

@st.cache_data(ttl=3)
def obtenir_bicis_actuals(id_estacio_buscar):
    url = "https://api.bsmsa.eu/ext/api/bsm/gbfs/v2/en/station_status"
    
    try:
        resposta = requests.get(url)
        # Comprovem que la petició ha anat bé
        if resposta.status_code == 200:
            dades = resposta.json()
            
            # Entrem a la llista on hi ha totes les estacions de Barcelona
            estacions = dades['data']['stations']
            
            # Busquem la nostra estació concreta
            for estacio in estacions:
                # Comparem l'ID de l'estació de l'API (station_id) amb l'ID que li passem a la funció
                if str(estacio['station_id']) == str(id_estacio_buscar):
                    return estacio['num_bikes_available']
                    
    except Exception as e:
        # Et recomano posar un st.error aquí temporalment si vols veure l'error real a la web
        # st.error(f"Error intern de l'API: {e}")
        return 0 
        
    return 0 # Si per algun motiu no troba l'ID

# CRÍTIC: Cridem a la funció passant-li l'id_seleccionat (el número), NO el text visual.
# L'id_seleccionat ja el tens calculat just a sobre per a la funció obtenir_estat_estacio!
bicis_ara_mateix = obtenir_bicis_actuals(id_seleccionat)

# --- 4. PREDICCIÓ ---
# Forcem el DataFrame a tenir l'ordre exacte de Kaggle abans de predir
ordre_correcte = ['hora_decimal', 'dia_setmana', 'latitude', 'longitude', 'temperature_2m', 'pluja_activa', 'status_num', 'bicis_estat_anterior']
input_dades = pd.DataFrame([[hora_decimal, dia_setmana, lat, lon, temp_actual, pluja_actual, status_actual, bicis_ara_mateix]], 
                           columns=ordre_correcte)

# Això ens ensenyarà la taula a la web per "espiar" què rep la IA
st.write("**Dades enviades al model:**")
st.write(input_dades)

# Fem la predicció NOMÉS quan es clica el botó
if st.button("Consultar Bicis Disponibles"):
    prediccio = model_bicing_bosc_definitiu.predict(input_dades)[0]
    
    st.metric(label="Bicicletes disponibles estimades", value=f"{round(prediccio, 1)}")
    
    if prediccio < 1:
        st.error("L'estació probablement no en tindrà cap.")
    elif prediccio < 3:
        st.warning("Quedaran molt poques bicis.")
    elif prediccio < 6:
        st.success("Hi haurà bicis suficients.")
    else:
        st.success("Hi haurà moltes bicis.")
