import streamlit as st
import requests
from google import genai
from google.genai import types
from notion_client import Client

# 1. Configuración de la interfaz web para el equipo
st.set_page_config(page_title="Bibliotecario START", page_icon="📚", layout="centered")
st.title("📚 El Bibliotecario de START Quito")
st.write("Pregúntame en inglés o español dónde encontrar documentos o información en Notion.")

# 2. Inicialización segura de credenciales (OAuth de Notion + Gemini)
# Configura estos nombres exactos en tus Streamlit Secrets
CLIENT_ID = st.secrets["NOTION_CLIENT_ID"]
CLIENT_SECRET = st.secrets["NOTION_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["NOTION_REDIRECT_URI"]  # Ej: https://startquito.streamlit.app
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
NOTION_PAGE_ID = st.secrets.get("NOTION_PAGE_ID", None)

# Inicializar cliente de Gemini
client_gemini = genai.Client(api_key=GEMINI_API_KEY)

# 3. Flujo Automático de Handshake OAuth 2.0
if "notion_oauth_token" not in st.session_state:
    st.session_state["notion_oauth_token"] = None

# Capturar parámetros inyectados por Notion en la URL (?code=...)
url_params = st.query_params

if not st.session_state["notion_oauth_token"] and "code" in url_params:
    auth_code = url_params["code"]
    
    with st.spinner("Estableciendo conexión segura con tu cuenta de Notion..."):
        try:
            response = requests.post(
                "https://api.notion.com/v1/oauth/token",
                auth=(CLIENT_ID, CLIENT_SECRET),
                json={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": REDIRECT_URI
                },
                headers={"Content-Type": "application/json"}
            )
            datos_auth = response.json()
            
            if "access_token" in datos_auth:
                st.session_state["notion_oauth_token"] = datos_auth["access_token"]
                # Limpiar el código de la URL visual para dejar una experiencia limpia
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"Error de autenticación: {datos_auth.get('error_description', 'Error Desconocido')}")
        except Exception as e:
            st.error(f"Fallo en el protocolo de enlace OAuth: {e}")

# Si no hay token de acceso, forzar el botón de Login y detener ejecución limpia
if not st.session_state["notion_oauth_token"]:
    auth_url = (
        f"https://api.notion.com/v1/oauth/authorize?"
        f"client_id={CLIENT_ID}&response_type=code&owner=user&redirect_uri={REDIRECT_URI}"
    )
    st.warning("⚠️ Para consultar al Bibliotecario, primero debes autorizar el acceso a tu espacio de trabajo.")
    st.link_button("🔐 Vincular mi cuenta de Notion", auth_url, use_container_width=True)
    st.stop()

# Inicializar el cliente de Notion una vez que el token existe
notion = Client(auth=st.session_state["notion_oauth_token"])


# 4. Función optimizada para extraer el mapa de conocimiento
@st.cache_data(ttl=1800)  # Guarda en caché por 30 minutos
def cargar_contexto_notion():
    contexto = ""
    
    # Estrategia Principal: Leer bloques de la página raíz compartida
    if NOTION_PAGE_ID:
        try:
            bloques = notion.blocks.children.list(block_id=NOTION_PAGE_ID).get("results", [])
            for bloque in bloques:
                tipo = bloque.get("type")
                if tipo in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "child_page"]:
                    if tipo == "child_page":
                        titulo_sub = bloque.get("child_page", {}).get("title", "Subpágina")
                        contexto += f"Subpágina detectada: {titulo_sub}\n"
                    else:
                        contenido = bloque.get(tipo, {}).get("rich_text", [])
                        if contenido:
                            texto = contenido[0].get("text", {}).get("content", "")
                            contexto += f"{texto}\n"
            if contexto:
                return f"Estructura interna de la Página Principal:\n{contexto}"
        except Exception:
            pass

    # Estrategia de Respaldo: Búsqueda global si el ID no está disponible
    try:
        paginas = notion.search(filter={"property": "object", "value": "page"}).get("results", [])
        for page in paginas:
            titulo = "Sin Título"
            properties = page.get("properties", {})
            for prop in properties.values():
                if prop.get("type") == "title" and prop.get("title"):
                    titulo = prop["title"][0]["text"]["content"]
                    break
            url = page.get("url", "")
            contexto += f"Página o Sección: {titulo} | Enlace Directo: {url}\n"
    except Exception as e:
        contexto = f"Aviso de sincronización global: {e}."

    if not contexto:
        contexto = "No se detectaron recursos accesibles en este espacio."
        
    return contexto

# Sincronizar el contexto en segundo plano
with st.spinner("El bibliotecario está organizando los registros compartidos..."):
    notion_context = cargar_contexto_notion()


# 5. Persistencia del historial del chat visual
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# 6. Interacción del Agente (Flujo de consulta y recuperación de enlaces)
if user_query := st.chat_input("¿Qué documento o sección estás buscando hoy?"):
    st.chat_message("user").markdown(user_query)
    st.session_state.messages.append({"role": "user", "content": user_query})
    
    system_instruction = (
        "Eres el Bibliotecario de la organización START Quito. Tu único propósito es guiar de forma "
        "atenta y clara a los miembros del equipo a encontrar lo que necesitan en Notion. "
        "Responde con total fluidez en el mismo idioma de la pregunta.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Analiza la consulta y busca la sección adecuada en el mapa de conocimiento adjunto.\n"
        "2. Proporciona un resumen ejecutivo muy conciso de la información encontrada.\n"
        "3. Imprime siempre de forma clara, explícita y visible el ENLACE DIRECTO (URL) de la página de Notion correspondiente para que el usuario pueda hacer clic e ingresar directamente a revisar detalles adicionales.\n"
        "4. Si la información no está en el mapa, dile amablemente que no cuentas con registros de ello en el mapa actual.\n\n"
        f"MAPA DE CONOCIMIENTO DE NOTION DISPONIBLE:\n{notion_context}"
    )
    
    try:
        response = client_gemini.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_query,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            ),
        )
        bot_response = response.text
    except Exception as e:
        bot_response = f"Lo siento, experimenté una dificultad técnica al consultar al bibliotecario. Detalles: {e}"

    with st.chat_message("assistant"):
        st.markdown(bot_response)
    st.session_state.messages.append({"role": "assistant", "content": bot_response})
