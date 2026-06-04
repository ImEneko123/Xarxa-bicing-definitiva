import streamlit as st
import pickle
import pandas as pd
import datetime
import requests
import io
st.title("Predictor de Disponibilitat Bicing")
@st.cache_resource
def carregar_model_des_de_dropbox():
    url = "https://www.dropbox.com/scl/fi/a5uqlxapxfh7wisbsw5wc/model_bicing_bosc_definitiu.pkl?rlkey=ispa6kkcscw9ukxvdt8tpjcf0&st=7eefesuu&dl=1"
    
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

#Si no ha triat res encara, mostrem un avís i aturem l'execució de la web
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

#Calculem l'hora actual a Barcelona
ara = pd.Timestamp.now(tz='Europe/Madrid')

#Calculem el moment futur sumant els minuts
moment_futur = ara + pd.Timedelta(minutes=int(minuts_futur))

#Actualitzem les variables per a la IA amb el temps nou
hora_decimal = moment_futur.hour + (moment_futur.minute / 60.0)
dia_setmana = moment_futur.weekday() # 0=Dilluns

st.info(f"Predicció per a: **{moment_futur.strftime('%H:%M')}** ({moment_futur.strftime('%A')})")

import requests

def obtenir_clima_futur(lat, lon, hora_seleccionada):
    api_key = "c9dc5c80c2fb4a5195b153641260306" 
    
    # URL de previsió
    url = f"http://api.weatherapi.com/v1/forecast.json?key={api_key}&q={lat},{lon}&days=1&aqi=no&alerts=no"
    
    try:
        resposta = requests.get(url).json()
        
        index_hora = int(hora_seleccionada)
        dades_hora = resposta['forecast']['forecastday'][0]['hour'][index_hora]
        
        # Extraiem la temperatura
        temp_actual = dades_hora['temp_c']
        
        #Saber si plourà
        pluja_activa = dades_hora['will_it_rain']
        
        return temp_actual, pluja_activa

    except Exception as e:
        st.error(f"Error en connectar amb WeatherAPI: {e}")
        return 18.0, 0  # Pla B d'emergència si falla internet
   
# Cridem a la nova funció passant-li la latitud, longitud i l'hora
temp_actual, pluja_actual = obtenir_clima_futur(lat, lon, hora_decimal)

#Mostrem a la web el clima detectat per a aquella hora
st.write(f"**Clima previst per a aquesta hora:** {temp_actual}°C i {'amb pluja' if pluja_actual == 1 else 'sense pluja'}")

@st.cache_data(ttl=60)
def obtenir_dades_bicing_api(lat_estacio, lon_estacio):
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        # Obtenim informació d'estacions (lat/lon -> hash id)
        r_info = requests.get(
            'https://api.citybik.es/gbfs/3/bicing/station_information.json',
            headers=headers, timeout=10
        )
        r_status = requests.get(
            'https://api.citybik.es/gbfs/3/bicing/station_status.json',
            headers=headers, timeout=10
        )
        
        if r_info.status_code == 200 and r_status.status_code == 200:
            estacions_info = r_info.json()['data']['stations']
            estacions_status = r_status.json()['data']['stations']
            
            # Trobem l'estació més propera per coordenades
            millor_id = None
            millor_distancia = float('inf')
            for e in estacions_info:
                dist = abs(e['lat'] - lat_estacio) + abs(e['lon'] - lon_estacio)
                if dist < millor_distancia:
                    millor_distancia = dist
                    millor_id = e['station_id']
            
            # Busquem l'estat d'aquell id
            status_map = {e['station_id']: e for e in estacions_status}
            if millor_id and millor_id in status_map:
                estat = status_map[millor_id]
                is_active = estat.get('is_renting', False) and estat.get('is_installed', False)
                status_num = 1 if is_active else 0
                bicis = estat.get('num_vehicles_available', 0)
                return status_num, bicis
            
            st.warning("Estació no trobada a CityBikes.")
        else:
            st.error(f"Error CityBikes: info={r_info.status_code}, status={r_status.status_code}")
    
    except requests.exceptions.Timeout:
        st.error("Error: La petició ha superat el temps límit. Comprova la connexió.")
    except requests.exceptions.ConnectionError as e:
        st.error(f"Error de connexió: {e}")
    except Exception as e:
        st.error(f"Error inesperat: {type(e).__name__}: {e}")
    
    return 1, 0
status_actual, bicis_ara_mateix = obtenir_dades_bicing_api(lat, lon)
#-------------------------------------------------------Fer la Predicció-------------------------------------------
ordre_correcte = ['hora_decimal', 'dia_setmana', 'latitude', 'longitude', 'temperature_2m', 'pluja_activa', 'status_num', 'bicis_estat_anterior']
input_dades = pd.DataFrame([[hora_decimal, dia_setmana, lat, lon, temp_actual, pluja_actual, status_actual, bicis_ara_mateix]], 
                           columns=ordre_correcte)
#El que rep la IA
st.write("**Dades enviades al model:**")
st.write(input_dades)

# Fem la predicció quan es clica el botó
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
