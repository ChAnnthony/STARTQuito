import streamlit as st
from google import genai
from google.genai import types
from notion_client import Client

# 1. Configuración de la interfaz web para el equipo
st.set_page_config(page_title="Bibliotecario START", page_icon="📚", layout="centered")
st.title("📚 El Bibliotecario de START Quito")
st.write("Pregúntame en inglés o español dónde encontrar documentos o información en Notion.")

# 2. Inicialización segura de credenciales desde Streamlit Secrets
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
NOTION_PAGE_ID = st.secrets.get("NOTION_PAGE_ID", None)

# Inicializar los clientes oficiales actualizados
client_gemini = genai.Client(api_key=GEMINI_API_KEY)
notion = Client(auth=NOTION_TOKEN)

# 3. Función robusta para extraer el mapa de conocimiento (Páginas y Enlaces)
@st.cache_data(ttl=1800)  # Guarda en caché por 30 minutos para optimizar rendimiento
def cargar_contexto_notion():
    contexto = ""
    
    # Estrategia Principal: Leer bloques de una página raíz (Evita object_not_found)
    if NOTION_PAGE_ID:
        try:
            bloques = notion.blocks.children.list(block_id=NOTION_PAGE_ID).get("results", [])
            for bloque in bloques:
                tipo = bloque.get("type")
                if tipo in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "child_page"]:
                    if tipo == "child_page":
                        titulo_sub = bloque.get("child_page", {}).get("title", "Subpágina")
                        contexto += f"Subpágina interna detectada: {titulo_sub}\n"
                    else:
                        contenido = bloque.get(tipo, {}).get("rich_text", [])
                        if contenido:
                            texto = contenido[0].get("text", {}).get("content", "")
                            contexto += f"{texto}\n"
            if contexto:
                return f"Estructura interna de la Página Principal:\n{contexto}"
        except Exception:
            pass # Si falla el ID, avanza al plan de respaldo de forma silenciosa

    # Estrategia de Respaldo: Búsqueda global mapeando títulos y URLs
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
        contexto = f"Aviso de sincronización global: {e}. Por favor verifica el acceso de la integración en Notion."

    if not contexto:
        contexto = "No se detectaron recursos compartidos. Recuerda añadir la conexión en tu panel de Notion."
        
    return contexto

# Cargar la base de conocimiento en segundo plano
with st.spinner("El bibliotecario está ordenando los estantes de Notion..."):
    notion_context = cargar_contexto_notion()

# 4. Mantener la persistencia del historial del chat visual
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 5. Interacción del Agente con el Usuario (Flujo de Consulta y Enlaces)
if user_query := st.chat_input("¿Qué documento o sección estás buscando hoy?"):
    st.chat_message("user").markdown(user_query)
    st.session_state.messages.append({"role": "user", "content": user_query})
    
    # Instrucción Maestra del Sistema: Configura el rol estricto de Bibliotecario Orientador
    system_instruction = (
        "Eres el Bibliotecario de la organización START Quito. Tu único propósito es guiar de forma "
        "atenta y clara a los miembros del equipo a encontrar lo que necesitan en Notion. "
        "Responde con total fluidez en el mismo idioma de la pregunta.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Analiza la consulta y busca la sección adecuada en el mapa de conocimiento adjunto.\n"
        "2. Proporciona un resumen ejecutivo muy conciso de la información encontrada.\n"
        "3. Imprime siempre de forma clara y visible el ENLACE DIRECTO (URL) de la página de Notion correspondiente para que el usuario haga clic y revise detalles adicionales.\n"
        "4. Si la información no está en el mapa, dile amablemente que no la encontraste en los registros actuales.\n\n"
        f"MAPA DE CONOCIMIENTO DE NOTION DISPONIBLE:\n{notion_context}"
    )
    
    try:
        # Petición utilizando el cliente moderno estándar de Google (Evita el error 404 v1beta)
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
