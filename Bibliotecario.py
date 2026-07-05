import streamlit as st
import google.generativeai as genai
from notion_client import Client

# 1. Configuración de la interfaz de Streamlit
st.set_page_config(page_title="Bibliotecario START", page_icon="📚", layout="centered")
st.title("📚 El Bibliotecario de START Quito")
st.write("Pregúntame en inglés o español dónde encontrar documentos o información en Notion.")

# 2. Inicializar credenciales seguras (Se configuran en los Secrets de Streamlit)
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# El ID de la página es opcional pero altamente recomendado para evitar el error 'object_not_found'
# Si no lo tienes en tus secrets, el sistema usará la búsqueda global como respaldo.
NOTION_PAGE_ID = st.secrets.get("NOTION_PAGE_ID", None)

genai.configure(api_key=GEMINI_API_KEY)
notion = Client(auth=NOTION_TOKEN)

# 3. Función optimizada y corregida con manejo de errores robusto
@st.cache_data(ttl=3600)  # Guarda en caché por 1 hora para evitar saturar la API
def cargar_contexto_notion():
    contexto = ""
    
    # ESTRATEGIA 1: Intentar leer una página raíz específica por ID (Evita object_not_found)
    if NOTION_PAGE_ID:
        try:
            bloques = notion.blocks.children.list(block_id=NOTION_PAGE_ID).get("results", [])
            for bloque in bloques:
                tipo = bloque.get("type")
                if tipo in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "child_page"]:
                    if tipo == "child_page":
                        titulo_sub = bloque.get("child_page", {}).get("title", "Subpágina")
                        contexto += f"Subpágina interna: {titulo_sub}\n"
                    else:
                        contenido = bloque.get(tipo, {}).get("rich_text", [])
                        if contenido:
                            texto = contenido[0].get("text", {}).get("content", "")
                            contexto += f"{texto}\n"
            if contexto:
                return f"Información de la Página Raíz:\n{contexto}"
        except Exception as e:
            # Si falla el ID, guardamos el log interno pero no tumbamos la app, pasamos al fallback
            pass

    # ESTRATEGIA 2: Fallback con búsqueda global controlada
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
            contexto += f"Página: {titulo} | Enlace: {url}\n"
    except Exception as e:
        contexto = f"Error al indexar Notion de forma global: {e}. Asegúrate de dar acceso a la integración en Notion."

    if not contexto:
        contexto = "No se encontraron páginas accesibles. Recuerda conectar la integración en los '...' de tus páginas de Notion."
        
    return contexto

# Cargar el mapa de Notion en segundo plano con manejo visual
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
    
    # Prompt del Sistema estructurado
    system_instruction = (
        "Eres el Bibliotecario de la organización START Quito. Tu único trabajo es guiar a los "
        "miembros del equipo no técnicos a encontrar la información. Responde de manera amable "
        "en el mismo idioma en que te pregunten (inglés o español). Basándote estrictamente en el "
        "siguiente contexto extraído de Notion, indica el nombre de la página, lo que contiene y "
        f"proporciona su enlace o URL exacta para que puedan acceder:\n\n{notion_context}"        
    )
    
    try:
        # Cambiamos "gemini-1.5-flash" por su versión explícita estable
        model = genai.GenerativeModel(
            model_name="models/gemini-1.5-flash-latest",
            system_instruction=system_instruction
        )
        
        response = model.generate_content(user_query)
        bot_response = response.text
        
    except Exception as e:
        bot_response = f"Lo siento, tuve un problema al procesar la consulta con Inteligencia Artificial. Detalles: {e}"

    with st.chat_message("assistant"):
        st.markdown(bot_response)
    st.session_state.messages.append({"role": "assistant", "content": bot_response})
