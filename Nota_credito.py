import streamlit as st
import requests
from datetime import date
from typing import List, Dict, Any

# ==========================
# CONFIGURACIÓN / LOGIN
# ==========================
st.set_page_config(page_title="Facturación Electrónica — IOM Panamá", layout="centered")

USUARIOS = {
    "Mispanama": "Maxilo2000",
    "usuario1": "password123",
}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align:center; color:#1c6758'>Acceso</h2>", unsafe_allow_html=True)
    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS and password == USUARIOS[usuario]:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    st.stop()

if st.sidebar.button("Cerrar sesión"):
    st.session_state["autenticado"] = False
    st.rerun()

# ==========================
# NINOX API CONFIG
# ==========================
API_TOKEN   = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"
TEAM_ID     = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"

BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS  = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# ==========================
# UTILIDADES NINOX
# ==========================
def _ninox_get(path: str, params: Dict[str, Any] | None = None, page_size: int = 200) -> List[Dict[str, Any]]:
    """Descarga todos los registros con paginación."""
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = dict(params or {})
        q.update({"limit": page_size, "offset": offset})
        url = f"{BASE_URL}{path}"
        r = requests.get(url, headers=HEADERS, params=q, timeout=30)
        if not r.ok:
            st.error(f"Error Ninox GET {path}: {r.status_code} — {r.text}")
            break
        batch = r.json() or []
        out.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return out

def obtener_clientes() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Clientes/records")

def obtener_productos() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Productos/records")

def obtener_facturas() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Facturas/records")

# --- NUEVO: Tabla "Nota de Credito" (con espacio; ruta URL-codificada) ---
def obtener_notas_credito() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Nota%20de%20Credito/records")

def calcular_siguiente_factura_no(facturas: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facturas:
        valor = (f.get("fields", {}) or {}).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            max_factura = max(max_factura, n)
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

# --- NUEVO: consecutivo propio para NC tomando "Credit No." de tu tabla ---
def calcular_siguiente_nc_no(notas: List[Dict[str, Any]]) -> str:
    max_nc = 0
    for n in notas:
        valor = (n.get("fields", {}) or {}).get("Credit No.", "")
        try:
            num = int(str(valor).strip() or 0)
            max_nc = max(max_nc, num)
        except Exception:
            continue
    return f"{max_nc + 1:08d}"

# ==========================
# CARGA / REFRESCO DE DATOS
# ==========================
if st.button("Actualizar datos de Ninox"):
    for k in ("clientes", "productos", "facturas", "notas_credito"):
        st.session_state.pop(k, None)

if "clientes" not in st.session_state:
    st.session_state["clientes"] = obtener_clientes()
if "productos" not in st.session_state:
    st.session_state["productos"] = obtener_productos()
if "facturas" not in st.session_state:
    st.session_state["facturas"] = obtener_facturas()
if "notas_credito" not in st.session_state:
    st.session_state["notas_credito"] = obtener_notas_credito()

clientes      = st.session_state["clientes"]
productos     = st.session_state["productos"]
facturas      = st.session_state["facturas"]
notas_credito = st.session_state["notas_credito"]

if not clientes:
    st.warning("No hay clientes en Ninox")
    st.stop()
if not productos:
    st.warning("No hay productos en Ninox")
    st.stop()

# ==========================
# MIGRACIÓN/INICIALIZACIÓN DE ÍTEMS
# ==========================
# Evita colisión con dict.items()
if "line_items" not in st.session_state:
    prev = st.session_state.get("items", [])
    st.session_state["line_items"] = prev if isinstance(prev, list) else []
    st.session_state.pop("items", None)

# ==========================
# TIPO DE DOCUMENTO
# ==========================
st.sidebar.markdown("## Tipo de documento")
doc_humano = st.sidebar.selectbox("Seleccione", ["Factura", "Nota de Crédito"])
DOC_MAP = {"Factura": "01", "Nota de Crédito": "06"}
doc_type = DOC_MAP[doc_humano]

# ==========================
# SELECCIÓN DE CLIENTE
# ==========================
st.header("Datos del Cliente")

nombres_clientes = [c.get("fields", {}).get("Nombre", f"Cliente {i}") for i, c in enumerate(clientes, start=1)]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente_fields: Dict[str, Any] = clientes[cliente_idx].get("fields", {}) or {}

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC",       value=cliente_fields.get("RUC", ""),        disabled=True)
    st.text_input("DV",        value=cliente_fields.get("DV", ""),         disabled=True)
    st.text_area ("Dirección", value=cliente_fields.get("Dirección", ""),  disabled=True)
with col2:
    st.text_input("Teléfono",  value=cliente_fields.get("Teléfono", ""),   disabled=True)
    st.text_input("Correo",    value=cliente_fields.get("Correo", ""),     disabled=True)

# ==========================
# NÚMERO DE DOCUMENTO
# ==========================
facturas_pendientes = [f for f in facturas if (f.get("fields", {}) or {}).get("Estado", "").strip().lower() == "pendiente"]

if doc_type == "01":
    if facturas_pendientes:
        opciones_facturas = [(f.get("fields", {}) or {}).get("Factura No.", "") for f in facturas_pendientes]
        idx_factura = st.selectbox(
            "Seleccione Factura Pendiente",
            range(len(opciones_facturas)),
            format_func=lambda x: str(opciones_facturas[x])
        )
        numero_preview = str(opciones_facturas[idx_factura])
    else:
        numero_preview = calcular_siguiente_factura_no(facturas)
else:  # "06" Nota de Crédito
    numero_preview = calcular_siguiente_nc_no(notas_credito)

st.text_input("Número de Documento Fiscal", value=numero_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# ==========================
# CAMPOS ESPECÍFICOS PARA NOTA DE CRÉDITO
# ==========================
motivo_nc = ""
factura_afectada = ""
if doc_type == "06":
    st.subheader("Datos de la Nota de Crédito")
    factura_afectada = st.text_input("Factura a afectar (Número Documento Fiscal original) *",
                                     value=st.session_state.get("factura_afectada", ""))
    motivo_nc = st.text_input("Motivo / Información de interés *",
                              value=st.session_state.get("motivo_nc", ""))
    st.session_state["factura_afectada"] = factura_afectada
    st.session_state["motivo_nc"] = motivo_nc

# ==========================
# ÍTEMS
# ==========================
st.header("Agregar Productos / Conceptos")

nombres_productos = [
    f"{(p.get('fields', {}) or {}).get('Código','')} | {(p.get('fields', {}) or {}).get('Descripción','')}"
    for p in productos
]
prod_idx    = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_fields = productos[prod_idx].get("fields", {}) or {}

cantidad    = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = float(prod_fields.get("Precio Unitario", 0) or 0)
itbms_rate  = float(prod_fields.get("ITBMS", 0) or 0)   # ej. 0.07

if st.button("Agregar ítem"):
    valor_itbms = round(itbms_rate * cantidad * precio_unit, 2)
    st.session_state["line_items"].append({
        "codigo":         prod_fields.get("Código", ""),
        "descripcion":    prod_fields.get("Descripción", ""),
        "cantidad":       float(cantidad),
        "precioUnitario": float(precio_unit),
        "tasa":           float(itbms_rate),
        "valorITBMS":     float(valor_itbms),
    })

if st.session_state["line_items"]:
    st.write("#### Ítems del documento")
    for idx, i in enumerate(st.session_state["line_items"], start=1):
        st.write(f"{idx}. {i['codigo']} | {i['descripcion']} | Cant: {i['cantidad']:.2f} | P.U.: {i['precioUnitario']:.2f} | ITBMS: {i['valorITBMS']:.2f}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Limpiar Ítems"):
            st.session_state["line_items"] = []
    with c2:
        idx_del = st.number_input("Eliminar ítem #", min_value=0, value=0, step=1)
        if st.button("Eliminar"):
            if 0 < idx_del <= len(st.session_state["line_items"]):
                st.session_state["line_items"].pop(idx_del - 1)

# ==========================
# TOTALES
# ==========================
total_neto    = sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state["line_items"])
total_itbms   = sum(i["valorITBMS"] for i in st.session_state["line_items"])
total_total   = total_neto + total_itbms

st.write(f"**Total Neto:** {total_neto:.2f}   **ITBMS:** {total_itbms:.2f}   **Total:** {total_total:.2f}")

medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"])
emisor     = st.text_input("Nombre de quien emite el documento (obligatorio)", value=st.session_state.get("emisor", ""))
if emisor:
    st.session_state["emisor"] = emisor

# ==========================
# BACKEND DGI
# ==========================
BACKEND_URL = "https://ninox-factory-server.onrender.com"

if "pdf_bytes" not in st.session_state:
    st.session_state["pdf_bytes"] = None
    st.session_state["pdf_name"]  = None

def _ninox_refrescar_tablas():
    st.session_state["facturas"]      = obtener_facturas()
    st.session_state["notas_credito"] = obtener_notas_credito()

# ==========================
# BUILDER DE PAYLOAD
# ==========================
def armar_payload_documento(
    *,
    doc_type: str,
    numero_documento: str,
    fecha_emision: date,
    cliente_fields: Dict[str, Any],
    items: List[Dict[str, Any]],
    total_neto: float,
    total_itbms: float,
    total: float,
    medio_pago: str,
    motivo_nc: str = "",
    factura_afectada: str = "",
) -> Dict[str, Any]:

    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]
    # NC según tu XML: formatoCAFE=3, entregaCAFE=3, tipoVenta=""
    formato_cafe  = 3 if doc_type == "06" else 1
    entrega_cafe  = 3 if doc_type == "06" else 1
    tipo_venta    = "" if doc_type == "06" else 1
    info_interes  = (motivo_nc or "").strip() if doc_type == "06" else ""

    lista_items = []
    for i in items:
        precio_item = i["cantidad"] * i["precioUnitario"]
        valor_total = precio_item + i["valorITBMS"]
        tasa_itbms  = "01" if (i.get("tasa", 0) or 0) > 0 else "00"
        lista_items.append({
            "codigo":                  i.get("codigo") or "0",
            "descripcion":             i.get("descripcion") or "SIN DESCRIPCIÓN",
            "codigoGTIN":              "0",
            "cantidad":                f"{i['cantidad']:.2f}",
            "precioUnitario":          f"{i['precioUnitario']:.2f}",
            "precioUnitarioDescuento": "0.00",
            "precioItem":              f"{precio_item:.2f}",
            "valorTotal":              f"{valor_total:.2f}",
            "cantGTINCom":             f"{i['cantidad']:.2f}",
            "codigoGTINInv":           "0",
            "tasaITBMS":               tasa_itbms,
            "valorITBMS":              f"{i['valorITBMS']:.2f}",
            "cantGTINComInv":          f"{i['cantidad']:.2f}",
        })

    payload = {
        "documento": {
            "codigoSucursalEmisor": "0000",
            "tipoSucursal": "1",
            "datosTransaccion": {
                "tipoEmision": "01",
                "tipoDocumento": doc_type,  # "01" Factura | "06" Nota de Crédito
                "numeroDocumentoFiscal": str(numero_documento),
                "puntoFacturacionFiscal": "001",
                "fechaEmision": f"{fecha_emision.isoformat()}T09:00:00-05:00",
                "naturalezaOperacion": "01",
                "tipoOperacion": 1,
                "destinoOperacion": 1,
                "formatoCAFE": formato_cafe,
                "entregaCAFE": entrega_cafe,
                "envioContenedor": 1,
                "procesoGeneracion": 1,
                "tipoVenta": tipo_venta,
                "informacionInteres": info_interes,
                "cliente": {
                    "tipoClienteFE": "02" if (cliente_fields.get("RUC") or "").strip() else "01",
                    "tipoContribuyente": 1,
                    "numeroRUC": (cliente_fields.get("RUC", "") or "").replace("-", ""),
                    "digitoVerificadorRUC": cliente_fields.get("DV", ""),
                    "razonSocial": cliente_fields.get("Nombre", ""),
                    "direccion": cliente_fields.get("Dirección", ""),
                    "telefono1": cliente_fields.get("Teléfono", ""),
                    "correoElectronico1": cliente_fields.get("Correo", ""),
                    "pais": "PA",
                },
            },
            "listaItems": {"item": lista_items},
            "totalesSubTotales": {
                "totalPrecioNeto":    f"{total_neto:.2f}",
                "totalITBMS":         f"{total_itbms:.2f}",
                "totalMontoGravado":  f"{total_itbms:.2f}",
                "totalDescuento":     "0.00",
                "totalAcarreoCobrado":"0.00",
                "valorSeguroCobrado": "0.00",
                "totalFactura":       f"{total:.2f}",
                "totalValorRecibido": f"{total:.2f}",
                "vuelto":             "0.00",
                "tiempoPago":         "1" if doc_type == "01" else "3",
                "nroItems":           str(len(lista_items)),
                "totalTodosItems":    f"{total:.2f}",
                "listaFormaPago": {
                    "formaPago": [{
                        "formaPagoFact":    forma_pago_codigo,
                        "valorCuotaPagada": f"{total:.2f}",
                    }]
                },
            },
        }
    }

    # Referencia a la factura afectada (ajusta el nombre si tu backend espera otro nodo)
    if doc_type == "06" and factura_afectada.strip():
        payload["documento"]["datosTransaccion"]["documentoAfectado"] = {
            "numeroDocumentoFiscal": factura_afectada.strip()
        }

    return payload

# ==========================
# ENVIAR A DGI
# ==========================
if st.button("Enviar Documento a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite el documento.")
        st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe agregar al menos un ítem.")
        st.stop()
    if doc_type == "06":
        if not factura_afectada.strip():
            st.error("Para la Nota de Crédito debe indicar la Factura a afectar.")
            st.stop()
        if not motivo_nc.strip():
            st.error("Para la Nota de Crédito debe ingresar el motivo / información de interés.")
            st.stop()

    numero_documento = numero_preview

    try:
        payload = armar_payload_documento(
            doc_type=doc_type,
            numero_documento=numero_documento,
            fecha_emision=fecha_emision,
            cliente_fields=cliente_fields,
            items=st.session_state["line_items"],
            total_neto=total_neto,
            total_itbms=total_itbms,
            total=total_total,
            medio_pago=medio_pago,
            motivo_nc=motivo_nc,
            factura_afectada=factura_afectada,
        )

        url_envio = f"{BACKEND_URL}/enviar-factura"  # el backend decide según tipoDocumento
        r = requests.post(url_envio, json=payload, timeout=60)
        if r.ok:
            st.success(f"{doc_humano} enviada correctamente. Generando PDF…")
            st.session_state["line_items"] = []
            _ninox_refrescar_tablas()
            st.session_state["ultima_factura_no"] = str(numero_documento)

            # Intento de descarga PDF inmediata
            url_pdf = f"{BACKEND_URL}/descargar-pdf"
            pdf_payload = {
                "codigoSucursalEmisor":  "0000",
                "numeroDocumentoFiscal": str(numero_documento),
                "puntoFacturacionFiscal":"001",
                "tipoDocumento":         doc_type,
                "tipoEmision":           "01",
                "serialDispositivo":     "",
            }
            rpdf = requests.post(url_pdf, json=pdf_payload, stream=True, timeout=60)
            ct = rpdf.headers.get("content-type", "")
            if rpdf.ok and ct.startswith("application/pdf"):
                st.session_state["pdf_bytes"] = rpdf.content
                st.session_state["pdf_name"]  = f"{'NC' if doc_type=='06' else 'Factura'}_{numero_documento}.pdf"
                st.success("¡PDF generado y listo para descargar abajo!")
            else:
                st.session_state["pdf_bytes"] = None
                st.session_state["pdf_name"]  = None
                st.error("Documento enviado, pero no se pudo generar el PDF automáticamente.")
                try:
                    st.write(rpdf.json())
                except Exception:
                    st.write(rpdf.text)
        else:
            st.error("Error al enviar el documento.")
            try:
                st.write(r.json())
            except Exception:
                st.write(r.text)
    except Exception as e:
        st.error(f"Error de conexión con el backend: {e}")

# ==========================
# DESCARGA PDF
# ==========================
if st.session_state.get("pdf_bytes") and st.session_state.get("pdf_name"):
    st.markdown("---")
    st.header("Descargar PDF")
    st.download_button(
        label="Descargar PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_name"],
        mime="application/pdf",
    )

# ==========================
# INFO / AYUDA
# ==========================
with st.expander("Ayuda / Referencias"):
    st.markdown(
        """
        - Tablas Ninox: `Clientes`, `Productos`, `Facturas`, **`Nota de Credito`**.
        - Campos esperados:
          - **Clientes**: Nombre, RUC, DV, Dirección, Teléfono, Correo
          - **Productos**: Código, Descripción, Precio Unitario, ITBMS (decimal; ej. 0.07)
          - **Facturas**: Estado (use "Pendiente" para listar), "Factura No." (consecutivo)
          - **Nota de Credito**: **"Credit No."** (consecutivo NC)
        - **Tipo de documento**:
          - **Factura (01)**: formatoCAFE=1, entregaCAFE=1, tipoVenta=1.
          - **Nota de Crédito (06)**: formatoCAFE=3, entregaCAFE=3, tipoVenta="", requiere “Factura a afectar” + “Motivo”.
        - Envío a DGI vía backend: `/enviar-factura` y descarga `/descargar-pdf` pasando `tipoDocumento`.
        - Zona horaria/CAFE: fija 09:00 -05:00.
        """
    )
