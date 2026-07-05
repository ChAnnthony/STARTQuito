import streamlit as st
import google.generativeai as genai
from notion_client import Client

# 1. Configuración de la interfaz de Streamlit
st.set_page_config(page_title="Bibliotecario START", page_icon="📚", layout="centered")
st.title("📚 El Bibliotecario de START Quito")
st.write("Pregúntame en inglés o español dónde encontrar documentos o información en Notion.")

# 2. Inicializar credenciales seguras (Se configuran en la nube de Streamlit)
# 2. Inicializar credenciales seguras (Usa estos nombres exactos de texto)
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
notion = Client(auth=NOTION_TOKEN)

# 3. Función optimizada para extraer texto de Notion (Solo Lectura)
@st.cache_data(ttl=3600)  # Guarda en caché por 1 hora para no saturar la API
def cargar_contexto_notion():
    contexto = ""
    # Buscamos todas las páginas accesibles por la integración
    paginas = notion.search(filter={"property": "object", "value": "page"}).get("results", [])
    
    for page in paginas:
        titulo = "Sin Título"
        properties = page.get("properties", {})
        
        # Extraer el título dinámicamente según la estructura de Notion
        for prop in properties.values():
            if prop.get("type") == "title" and prop.get("title"):
                titulo = prop["title"][0]["text"]["content"]
                break
        
        url = page.get("url", "")
        contexto += f"Página: {titulo} | Enlace: {url}\n"
    
    return contexto

# Cargar el mapa de Notion en segundo plano
with st.spinner("Sincronizando el mapa de Notion..."):
    notion_context = cargar_contexto_notion()

# 4. Manejo del Historial del Chat en la interfaz
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 5. Lógica del Agente al recibir una pregunta
if user_query := st.chat_input("¿Qué estás buscando?"):
    st.chat_message("user").markdown(user_query)
    st.session_state.messages.append({"role": "user", "content": user_query})
    
    # Prompt del Sistema: Define el rol de Bibliotecario Estricto
    system_instruction = (
        "Eres el Bibliotecario de la organización START Quito. Tu único trabajo es guiar a los "
        "miembros del equipo no técnicos a encontrar la información. Responde en el mismo idioma "
        "en que te pregunten (inglés o español). Basándote estrictamente en el siguiente contexto de Notion, "
        f"indica el nombre de la página y proporciona su enlace exacto:\n\n{notion_context}"
    )
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_instruction
        )
        
        response = model.generate_content(user_query)
        bot_response = response.text
    except Exception as e:
        bot_response = "Lo siento, tuve un problema al consultar la base de datos de conocimiento."

    with st.chat_message("assistant"):
        st.markdown(bot_response)
    st.session_state.messages.append({"role": "assistant", "content": bot_response})
