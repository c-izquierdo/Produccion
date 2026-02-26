# -*- coding: utf-8 -*-
"""
APP PROYECTOS V2
Tabs: Datos / Taller / Lavado / Disponibilidad
"""

import math
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(page_title="Proyectos V2", layout="wide")
st.markdown(
    """
<style>
:root{
  --tabs-top: 3.25rem;     /* distancia desde arriba */
  --tabs-h: 3.0rem;        /* alto barra tabs */
  --sidebar-open-w: 21rem; /* ancho sidebar cuando está abierto (ajustable) */
}

/* Barra tabs fija */
.stTabs [data-baseweb="tab-list"]{
  position: fixed !important;
  top: var(--tabs-top);
  left: 0;
  right: 0;
  z-index: 10000;
  background: var(--background-color, white);
  border-bottom: 1px solid rgba(49, 51, 63, 0.15);
  padding-left: 4.5rem;
  padding-right: 1rem;
  overflow-x: auto;
  white-space: nowrap;
}

/* Empujar contenido para que no se tape bajo la barra */
.stTabs [data-baseweb="tab-panel"]{
  margin-top: var(--tabs-h);
}

/* ✅ Cuando el sidebar está ABIERTO: corre la barra tabs a la derecha */
body:has(section[data-testid="stSidebar"][aria-expanded="true"])
.stTabs [data-baseweb="tab-list"]{
  left: var(--sidebar-open-w) !important;
  width: calc(100% - var(--sidebar-open-w)) !important;
  padding-left: 1rem;
}
</style>
""",
    unsafe_allow_html=True
)

# ------------------------------

XLSX_PATH = Path("proyectos_v2.xlsx")
OLD_XLSX = Path("proyectos.xlsx")

ROWID_COL = "__rowid"

SHEETS = {
    "proyectos": "proyectos",
    "stock": "stock_dispo",
    "lavado": "lavado",
}

PROY_COLS = [
    "Proyecto",
    "Constructora",
    "Tipo",
    "Fecha_requerida",
    "M2",
    "Avance_pct",
    "Avance_m2",
    "Ritmo_esperado",
    "Inicio_obra",
    "Duracion_obra_meses",
    "Termino_obra",
    "WF600x2250_usado",
    "WF600x2250_nuevo",
    "CE600x1200_usado",
    "CE600x1200_nuevo",
    "Comentario",
]

DISPO_STOCK_COLS = [
    "Fecha",
    "WF600x2250_nuevo", "WF600x2250_usado",
    "CE600x1200_nuevo", "CE600x1200_usado",
    "Comentario",
]

LAVADO_COLS = [
    "Proyecto",
    "Constructora",
    "M2",
    "Avance",
    "Inicio",
    "Termino",
    "Fecha Requerida",
    "Ritmo",
    "Estado",
    "Holgura",
    "Inicio_prog",
]

def load_all_data():
    """Carga desde Excel (o crea vacíos) y normaliza proyectos."""
    if XLSX_PATH.exists():
        proy = pd.read_excel(XLSX_PATH, sheet_name="proyectos")
        stock = pd.read_excel(XLSX_PATH, sheet_name="stock_dispo")
        lav = pd.read_excel(XLSX_PATH, sheet_name="lavado")
    else:
        proy = pd.DataFrame(columns=PROY_COLS)
        stock = pd.DataFrame(columns=DISPO_STOCK_COLS)
        lav = pd.DataFrame(columns=LAVADO_COLS)

    # Normaliza tipo/fechas + autocompleta inicio_obra si está vacío
    proy = normalizar_proyectos(proy)
    stock = normalizar_stock(stock)
    lav = normalizar_lavado(lav)

    return proy, stock, lav



def save_all_data(proy, stock, lav):
    proy_to_save = normalizar_proyectos(proy.copy())

    stock_to_save = stock.copy()
    if "Fecha" in stock_to_save.columns:
        stock_to_save["Fecha"] = pd.to_datetime(stock_to_save["Fecha"], errors="coerce").dt.date

    lav_to_save = lav.copy()
    if "Fecha Requerida" in lav_to_save.columns:
        lav_to_save["Fecha Requerida"] = pd.to_datetime(lav_to_save["Fecha Requerida"], errors="coerce").dt.date
    if "Inicio_prog" in lav_to_save.columns:
        lav_to_save["Inicio_prog"] = pd.to_datetime(lav_to_save["Inicio_prog"], errors="coerce").dt.date

    try:
        with pd.ExcelWriter(XLSX_PATH, engine="openpyxl", mode="w") as writer:
            proy_to_save.to_excel(writer, sheet_name="proyectos", index=False)
            stock_to_save.to_excel(writer, sheet_name="stock_dispo", index=False)
            lav_to_save.to_excel(writer, sheet_name="lavado", index=False)
    except PermissionError:
        st.error("No pude guardar el Excel. Probablemente está abierto. Ciérralo y vuelve a intentar.")

def df_to_markdown_safe(df: pd.DataFrame, index: bool = False) -> str:
    """Convierte DataFrame a markdown sin fallar si falta 'tabulate'."""
    if df is None or df.empty:
        return "_(sin datos)_\n"

    try:
        return df.to_markdown(index=index)
    except Exception:
        d = df.copy()
        if not index:
            d = d.reset_index(drop=True)

        cols = [str(c) for c in d.columns]
        header = "| " + " | ".join(cols) + " |\n"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |\n"

        rows = []
        for _, r in d.iterrows():
            rows.append("| " + " | ".join([str(x) if pd.notna(x) else "" for x in r.values]) + " |\n")
        return header + sep + "".join(rows)

def df_to_teams_codeblock(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        body = "(sin datos)"
    else:
        try:
            from tabulate import tabulate
            body = tabulate(df, headers="keys", tablefmt="psql", showindex=False)
        except Exception:
            # fallback: TSV alineado “razonable”
            body = df.to_csv(sep="\t", index=False)
    return f"```\n{body}\n```"

def df_to_pretty_text(df: pd.DataFrame) -> str:
    """Texto alineado para TXT (ideal para Teams en bloque de código)."""
    if df is None or df.empty:
        return "(sin datos)"
    try:
        from tabulate import tabulate
        return tabulate(df, headers="keys", tablefmt="psql", showindex=False)
    except Exception:
        # fallback TSV (menos bonito, pero estable)
        return df.to_csv(sep="\t", index=False)

def df_to_teams_codeblock(df: pd.DataFrame) -> str:
    """Esto es lo que copias/pegas en Teams para que NO se desordene."""
    body = df_to_pretty_text(df)
    return f"{body}"

def copy_button(text: str, label: str, key: str):
    """Botón copiar al portapapeles usando JS (funciona en la mayoría de navegadores)."""
    # Escapar para JS literal
    safe = (
        text.replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("\r", "")
    )
    html = f"""
    <div style="display:flex; gap:.5rem; align-items:center;">
      <button id="{key}" style="
        padding:0.35rem 0.7rem; border:1px solid #ccc; border-radius:8px;
        background:white; cursor:pointer;">
        {label}
      </button>
      <span id="{key}_msg" style="font-size:0.9rem; opacity:0.8;"></span>
    </div>
    <script>
      const btn = document.getElementById("{key}");
      const msg = document.getElementById("{key}_msg");
      btn.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText(`{safe}`);
          msg.textContent = "✅ Copiado";
          setTimeout(() => msg.textContent = "", 1500);
        }} catch (e) {{
          msg.textContent = "⚠️ No se pudo copiar (permiso del navegador)";
        }}
      }});
    </script>
    """
    components.html(html, height=50)

def export_block(df: pd.DataFrame, *, name: str, key_prefix: str):
    """Bloque estándar: Copiar Teams + export MD + export TXT + preview opcional."""
    md = df_to_markdown_safe(df, index=False)
    txt = df_to_pretty_text(df)
    teams = df_to_teams_codeblock(df)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.download_button(
            f"⬇️ {name} (Markdown .md)",
            data=md,
            file_name=f"{key_prefix}.md",
            mime="text/markdown",
            key=f"dl_{key_prefix}_md",
        )
    with col2:
        st.download_button(
            f"⬇️ {name} (Texto .txt)",
            data=txt,
            file_name=f"{key_prefix}.txt",
            mime="text/plain",
            key=f"dl_{key_prefix}_txt",
        )
    with col3:
        copy_button(teams, f"📋 Copiar para Teams", key=f"cp_{key_prefix}")

# =========================
# Editor estable (fix definitivo) - igual al app.py
# =========================
ROWID_COL = "__rowid"

def ensure_rowid(df: pd.DataFrame, col: str = ROWID_COL) -> pd.DataFrame:
    df = df.copy()
    if col not in df.columns:
        df[col] = [uuid.uuid4().hex for _ in range(len(df))]
    else:
        df[col] = df[col].astype(str)
        mask = df[col].isna() | (df[col].str.strip() == "") | (df[col].str.lower() == "nan")
        if mask.any():
            df.loc[mask, col] = [uuid.uuid4().hex for _ in range(int(mask.sum()))]

    # Garantiza unicidad
    dup = df[col].duplicated(keep=False)
    if dup.any():
        seen = set()
        new_vals = []
        for v in df[col].tolist():
            if v in seen:
                new_vals.append(uuid.uuid4().hex)
            else:
                seen.add(v)
                new_vals.append(v)
        df[col] = new_vals

    # Forzar __rowid al final
    if col in df.columns:
        cols = [c for c in df.columns if c != col] + [col]
        df = df[cols]

    return df

def drop_internal_cols(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore")

def _apply_editor_delta(df_key: str, widget_key: str, schema_fn):
    delta = st.session_state.get(widget_key)
    if not isinstance(delta, dict):
        return

    rowids_view = st.session_state.get(f"{widget_key}__rowids", [])
    if not isinstance(rowids_view, list):
        rowids_view = []

    base = st.session_state.get(df_key)
    if base is None:
        return

    base = ensure_rowid(base)
    base_i = base.set_index(ROWID_COL, drop=False)

    # 1) Ediciones
    edited_rows = delta.get("edited_rows", {}) or {}
    for rpos, changes in edited_rows.items():
        try:
            rid = rowids_view[int(rpos)]
        except Exception:
            continue
        if rid not in base_i.index:
            continue
        for col, val in (changes or {}).items():
            if col == ROWID_COL:
                continue
            base_i.at[rid, col] = val

    # 2) Borrados
    deleted_rows = delta.get("deleted_rows", []) or []
    del_rids = []
    for rpos in deleted_rows:
        try:
            del_rids.append(rowids_view[int(rpos)])
        except Exception:
            pass
    if del_rids:
        base_i = base_i.drop(index=[r for r in del_rids if r in base_i.index], errors="ignore")

    # 3) Agregados
    added_rows = delta.get("added_rows", []) or []
    if added_rows:
        new_df = pd.DataFrame(added_rows)
        new_df = ensure_rowid(new_df)
        # Alinea columnas a base
        for c in base_i.columns:
            if c not in new_df.columns:
                new_df[c] = np.nan
        new_df = new_df[base_i.columns]
        base_i = pd.concat([base_i, new_df], axis=0)

    out = base_i.reset_index(drop=True)

    # Normaliza esquema preservando __rowid
    out = schema_fn(out) if schema_fn is not None else ensure_rowid(out)
    st.session_state[df_key] = out

def stable_data_editor(
    *,
    df_key: str,
    widget_key: str,
    column_config: dict | None = None,
    schema_fn=None,
    view_df: pd.DataFrame | None = None,
    height: int | None = None,
    num_rows: str = "dynamic",
):
    if df_key not in st.session_state:
        st.session_state[df_key] = pd.DataFrame()

    st.session_state[df_key] = ensure_rowid(st.session_state[df_key])

    df_base = st.session_state[df_key]
    view_df = df_base if view_df is None else view_df
    view_df = ensure_rowid(view_df)

    editor_df = view_df.copy()
    if ROWID_COL in editor_df.columns:
        editor_df = editor_df[[c for c in editor_df.columns if c != ROWID_COL] + [ROWID_COL]]

    st.session_state[f"{widget_key}__rowids"] = editor_df[ROWID_COL].astype(str).tolist()

    def _cb():
        _apply_editor_delta(df_key, widget_key, schema_fn)

    if column_config is None:
        column_config = {}
    column_config = dict(column_config)
    column_config[ROWID_COL] = st.column_config.TextColumn("__rowid", disabled=True, width="small")

    st.data_editor(
        editor_df,
        num_rows=num_rows,
        hide_index=True,
        use_container_width=True,
        column_config=column_config,
        key=widget_key,
        on_change=_cb,
        height=height,
    )

    return st.session_state[df_key]

def schema_proyectos_keep_rowid(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_rowid(df)
    rid = out[ROWID_COL].astype(str).copy()

    core = drop_internal_cols(out).copy()
    for c in PROY_COLS:
        if c not in core.columns:
            core[c] = pd.NA
    core = core[PROY_COLS].copy()

    core["Tipo"] = core["Tipo"].fillna("").astype(str).str.strip()

    # fechas SOLO date (sin horas)
    core["Fecha_requerida"] = pd.to_datetime(core["Fecha_requerida"], errors="coerce").dt.date
    core["Inicio_obra"] = pd.to_datetime(core["Inicio_obra"], errors="coerce").dt.date

    # Numéricos
    core["M2"] = pd.to_numeric(core["M2"], errors="coerce").fillna(0)
    core["Avance_pct"] = pd.to_numeric(core["Avance_pct"], errors="coerce").fillna(0).clip(0, 100)
    core["Ritmo_esperado"] = pd.to_numeric(core["Ritmo_esperado"], errors="coerce")
    core["Duracion_obra_meses"] = pd.to_numeric(core["Duracion_obra_meses"], errors="coerce")

    # ✅ Calcula Avance_m2 desde % y M2
    core["Avance_m2"] = (core["M2"] * (core["Avance_pct"] / 100)).round(2)

    # Autocompletar Inicio_obra solo si está vacío
    mask = pd.isna(core["Inicio_obra"]) & pd.notna(core["Fecha_requerida"])
    core.loc[mask, "Inicio_obra"] = core.loc[mask, "Fecha_requerida"]

    # ✅ Termino_obra = Inicio_obra + Duracion_obra_meses (aprox 30 días/mes)
    core["Termino_obra"] = pd.NA
    ini_dt = pd.to_datetime(core["Inicio_obra"], errors="coerce")
    dur = core["Duracion_obra_meses"]
    mask_term = ini_dt.notna() & dur.notna() & (dur > 0)
    core.loc[mask_term, "Termino_obra"] = (
        ini_dt.loc[mask_term] + pd.to_timedelta(dur.loc[mask_term] * 30, unit="D")
    ).dt.date

    # ✅ Comentario siempre texto
    core["Comentario"] = core["Comentario"].fillna("").astype(str)

    core[ROWID_COL] = rid.values
    return ensure_rowid(core)

def schema_stock_keep_rowid(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_rowid(df)
    rid = out[ROWID_COL].astype(str).copy()

    core = drop_internal_cols(out).copy()
    for c in DISPO_STOCK_COLS:
        if c not in core.columns:
            core[c] = pd.NA
    core = core[DISPO_STOCK_COLS].copy()

    core["Fecha"] = pd.to_datetime(core["Fecha"], errors="coerce").dt.date  # sin horas
    for c in ["WF600x2250_nuevo","WF600x2250_usado","CE600x1200_nuevo","CE600x1200_usado"]:
        core[c] = pd.to_numeric(core[c], errors="coerce").fillna(0)
    core["Comentario"] = core["Comentario"].fillna("").astype(str)

    core[ROWID_COL] = rid.values
    return ensure_rowid(core)

def schema_lavado_keep_rowid(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_rowid(df)
    rid = out[ROWID_COL].astype(str).copy()

    core = drop_internal_cols(out).copy()
    for c in LAVADO_COLS:
        if c not in core.columns:
            core[c] = pd.NA
    core = core[LAVADO_COLS].copy()

    # fechas sin horas
    for c in ["Inicio","Termino","Fecha Requerida","Inicio_prog"]:
        core[c] = pd.to_datetime(core[c], errors="coerce").dt.date

    core["Proyecto"] = core["Proyecto"].fillna("").astype(str)
    core["Constructora"] = core["Constructora"].fillna("").astype(str)

    core[ROWID_COL] = rid.values
    return ensure_rowid(core)


# ============================================================
# ALTURA DINÁMICA (MUESTRA TODAS LAS FILAS)
# ============================================================

def _df_height(df, header_px=45, row_px=35, min_px=180):
    if df is None:
        return min_px
    n = len(df)
    return max(min_px, header_px + row_px * max(1, n))


# ============================================================
# ROWID ESTABLE
# ============================================================

def ensure_rowid(df):
    df = df.copy()
    if ROWID_COL not in df.columns:
        df[ROWID_COL] = [uuid.uuid4().hex for _ in range(len(df))]
    return df


def drop_internal_cols(df):
    return df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore")

def normalizar_proyectos(df_proy: pd.DataFrame) -> pd.DataFrame:
    df = df_proy.copy()

    # Asegurar columnas
    for c in ["Fecha_requerida", "Inicio_obra", "Tipo"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Normalizar Tipo a texto limpio
    df["Tipo"] = df["Tipo"].fillna("").astype(str).str.strip()

    # Normalizar fechas a "solo fecha" (sin hora)
    df["Fecha_requerida"] = pd.to_datetime(df["Fecha_requerida"], errors="coerce").dt.date
    df["Inicio_obra"] = pd.to_datetime(df["Inicio_obra"], errors="coerce").dt.date

    # Autocompletar Inicio_obra SOLO si está vacío
    mask = df["Inicio_obra"].isna() & df["Fecha_requerida"].notna()
    df.loc[mask, "Inicio_obra"] = df.loc[mask, "Fecha_requerida"]

    return df

def normalizar_stock(df_stock: pd.DataFrame) -> pd.DataFrame:
    df = df_stock.copy()
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    return df

def normalizar_lavado(df_lav: pd.DataFrame) -> pd.DataFrame:
    df = df_lav.copy()
    for c in ["Inicio", "Termino", "Fecha Requerida", "Inicio_prog"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df
    
# ============================================================
# PROGRAMACIÓN
# ============================================================

def next_bday(ts):
    ts = pd.Timestamp(ts).normalize()
    while ts.weekday() >= 5:
        ts += pd.Timedelta(days=1)
    return ts


def ceil_days(m2_rest, ritmo):
    if m2_rest <= 0 or ritmo <= 0:
        return 0
    return int(math.ceil(m2_rest / ritmo))


def programa_linea(df, ritmo_base, hoy):
    df = df.copy()

    # --- Fecha requerida (acepta 2 nombres) ---
    if "Fecha Requerida" in df.columns:
        req = pd.to_datetime(df["Fecha Requerida"], errors="coerce")
    elif "Fecha_requerida" in df.columns:
        req = pd.to_datetime(df["Fecha_requerida"], errors="coerce")
    else:
        req = pd.Series(pd.NaT, index=df.index)

    # ✅ Ordenar por fecha requerida más cercana (NaT al final)
    order = req.fillna(pd.Timestamp.max).sort_values().index
    df = df.loc[order].reset_index(drop=True)
    req = req.loc[order].reset_index(drop=True)

    # --- columnas base ---
    m2 = pd.to_numeric(df.get("M2", 0), errors="coerce").fillna(0)
    avance = pd.to_numeric(df.get("Avance", 0), errors="coerce").fillna(0)

    # Ritmo (acepta Ritmo o Ritmo_esperado)
    col_ritmo = "Ritmo" if "Ritmo" in df.columns else ("Ritmo_esperado" if "Ritmo_esperado" in df.columns else None)
    if col_ritmo:
        ritmo = pd.to_numeric(df[col_ritmo], errors="coerce").fillna(ritmo_base)
    else:
        ritmo = pd.Series(ritmo_base, index=df.index)

    inicios, fines, holguras, estados = [], [], [], []
    fecha_actual = next_bday(hoy)

    for i in range(len(df)):
        restante = float(m2.iloc[i]) * (1 - float(avance.iloc[i]) / 100.0)
        dias = ceil_days(restante, float(ritmo.iloc[i]))

        inicio = fecha_actual
        fin = inicio + pd.Timedelta(days=max(0, dias))

        inicios.append(inicio.date())
        fines.append(fin.date())

        # Holgura y Estado (días hábiles)
        req_i = req.iloc[i]
        if pd.isna(req_i):
            holguras.append(np.nan)
            estados.append("S/D")
        else:
            fin_d = pd.Timestamp(fin).normalize()
            req_d = pd.Timestamp(req_i).normalize()

            if fin_d <= req_d:
                h = np.busday_count(fin_d.date(), req_d.date())
                estados.append("EN PLAZO")
                holguras.append(int(h))
            else:
                h = -np.busday_count(req_d.date(), fin_d.date())
                estados.append("ATRASADO")
                holguras.append(int(h))

        fecha_actual = fin  # encadena

    return pd.DataFrame({
        "Proyecto": df["Proyecto"] if "Proyecto" in df.columns else "",
        "Constructora": df["Constructora"] if "Constructora" in df.columns else "",
        "Tipo": df["Tipo"] if "Tipo" in df.columns else "",
        "M2": m2,
        "Avance %": avance,
        "Fecha Requerida": req.dt.date,
        "Inicio prog": inicios,
        "Fin prog": fines,
        "Holgura": holguras,
        "Estado": estados,
    })


    return pd.DataFrame({
        "Proyecto": df["Proyecto"] if "Proyecto" in df.columns else "",
        "Constructora": df["Constructora"] if "Constructora" in df.columns else "",
        "Tipo": df["Tipo"] if "Tipo" in df.columns else "",
        "M2": m2,
        "Avance %": avance,
        "Fecha Requerida": req.dt.date,
        "Inicio prog": inicios,
        "Fin prog": fines,
        "Holgura": holguras,
        "Estado": estados,
    })



# ============================================================
# DISPONIBILIDAD (4 GRÁFICOS)
# ============================================================

# ============================================================
# DISPONIBILIDAD (IGUAL APP ANTERIOR: STOCK + USO EN OBRA + LÍNEA TOTAL)
# ============================================================

def _clean_stock_dispo_v2(stock: pd.DataFrame) -> pd.DataFrame:
    """Normaliza stock_dispo para simulación (Fecha datetime + numéricos)."""
    df = stock.copy()

    if "Fecha" not in df.columns:
        df["Fecha"] = pd.NaT

    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.normalize()

    for c in ["WF600x2250_nuevo", "WF600x2250_usado", "CE600x1200_nuevo", "CE600x1200_usado"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(float)

    df = df.dropna(subset=["Fecha"]).sort_values("Fecha")
    return df


def _obras_from_proyectos_v2(proy: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte tabla Proyectos (V2) en 'obras_dispo' para simulación:
    - Usa Inicio_obra (si existe) o Fecha_requerida como Inicio_obra
    - Termino_obra = Inicio_obra + Duracion_obra_meses * 30 días (aprox)
    - Tipos:
        Venta => VENTA
        Arriendo / Arriendo MO => ARRIENDO
        Reparación => se EXCLUYE de disponibilidad
    """
    df = proy.copy()

    # Asegurar columnas
    for c in [
        "Proyecto", "Constructora", "Tipo",
        "Inicio_obra", "Fecha_requerida", "Duracion_obra_meses",
        "WF600x2250_usado", "WF600x2250_nuevo",
        "CE600x1200_usado", "CE600x1200_nuevo",
        "Comentario",
    ]:
        if c not in df.columns:
            df[c] = pd.NA

    # Limpieza base
    df["Proyecto"] = df["Proyecto"].fillna("").astype(str)
    df["Constructora"] = df["Constructora"].fillna("").astype(str)

    tipo_raw = df["Tipo"].fillna("").astype(str).str.strip().str.upper()
    # Excluir Reparación
    df = df[tipo_raw != "REPARACIÓN"].copy()
    tipo_raw = df["Tipo"].fillna("").astype(str).str.strip().str.upper()

    # Mapear tipos
    tipo_map = {
        "VENTA": "VENTA",
        "ARRIENDO": "ARRIENDO",
        "ARRIENDO MO": "ARRIENDO",
    }
    df["Tipo_norm"] = tipo_raw.map(tipo_map).fillna(tipo_raw)

    # Fechas
    ini = pd.to_datetime(df["Inicio_obra"], errors="coerce")
    req = pd.to_datetime(df["Fecha_requerida"], errors="coerce")
    df["Inicio_obra_norm"] = ini
    mask_ini = df["Inicio_obra_norm"].isna() & req.notna()
    df.loc[mask_ini, "Inicio_obra_norm"] = req.loc[mask_ini]

    df["Duracion_obra_meses"] = pd.to_numeric(df["Duracion_obra_meses"], errors="coerce")
    df["Termino_obra_norm"] = pd.NaT
    mask_dur = df["Inicio_obra_norm"].notna() & df["Duracion_obra_meses"].notna()
    df.loc[mask_dur, "Termino_obra_norm"] = df.loc[mask_dur, "Inicio_obra_norm"] + pd.to_timedelta(
        df.loc[mask_dur, "Duracion_obra_meses"] * 30, unit="D"
    )

    # Piezas numéricas
    for c in ["WF600x2250_usado", "WF600x2250_nuevo", "CE600x1200_usado", "CE600x1200_nuevo"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(float)

    # Filtrar proyectos sin nombre
    df = df[df["Proyecto"].str.strip() != ""].copy()

    # Formato final tipo "obras_dispo"
    out = pd.DataFrame({
        "Proyecto": df["Proyecto"],
        "Constructora": df["Constructora"],
        "Tipo": df["Tipo_norm"],
        "Inicio_obra": df["Inicio_obra_norm"],
        "Duracion_obra_meses": df["Duracion_obra_meses"],
        "Termino_obra": df["Termino_obra_norm"],
        "WF600x2250_usado": df["WF600x2250_usado"],
        "WF600x2250_nuevo": df["WF600x2250_nuevo"],
        "CE600x1200_usado": df["CE600x1200_usado"],
        "CE600x1200_nuevo": df["CE600x1200_nuevo"],
        "Comentario": df.get("Comentario", "").fillna("").astype(str),
    })
    return out


def _simular_pieza(stock_df: pd.DataFrame, obras_df: pd.DataFrame, pieza_prefix: str):
    """
    Copiado de la app anterior: simula stock nuevo/usado/total en el tiempo.
    Para VENTA: descuenta nuevo desde Inicio_obra (no vuelve).
    Para ARRIENDO: descuenta durante la obra y devuelve TODO como USADO al término.
    """
    col_usado = f"{pieza_prefix}_usado"
    col_nuevo = f"{pieza_prefix}_nuevo"

    stock = stock_df.copy()
    if stock.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    obras = obras_df.copy()
    obras = obras[~obras["Inicio_obra"].isna()].copy()

    ventas = obras[obras["Tipo"].str.upper() == "VENTA"].copy()
    arrs = obras[(obras["Tipo"].str.upper() == "ARRIENDO") & (~obras["Termino_obra"].isna())].copy()

    fechas_evt = set(stock["Fecha"].dt.normalize())
    fechas_evt.update(ventas["Inicio_obra"].dt.normalize())
    fechas_evt.update(arrs["Inicio_obra"].dt.normalize())
    fechas_evt.update(arrs["Termino_obra"].dt.normalize())

    if not fechas_evt:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    fechas = sorted(fechas_evt)

    stock_by_date = stock.groupby(stock["Fecha"].dt.normalize())[[f"{pieza_prefix}_nuevo", f"{pieza_prefix}_usado"]].sum()
    ventas_by_date = ventas.groupby(ventas["Inicio_obra"].dt.normalize())[col_nuevo].sum()

    arrs = arrs.copy()
    arrs["Inicio_norm"] = arrs["Inicio_obra"].dt.normalize()
    arrs["Termino_norm"] = arrs["Termino_obra"].dt.normalize()

    arrs_start = arrs.groupby("Inicio_norm")[[col_usado, col_nuevo]].sum()

    terminos_map = {}
    for idx, row in arrs.iterrows():
        d_term = row["Termino_norm"]
        terminos_map.setdefault(d_term, []).append(idx)

    registros = []
    stock_nuevo = 0.0
    stock_usado = 0.0

    for d in fechas:
        # 1) Entradas de stock (inicial/compras)
        if d in stock_by_date.index:
            stock_nuevo += float(stock_by_date.loc[d, f"{pieza_prefix}_nuevo"])
            stock_usado += float(stock_by_date.loc[d, f"{pieza_prefix}_usado"])

        # 2) Devolución arriendos que terminan hoy (todo vuelve como usado)
        if d in terminos_map:
            for idx in terminos_map[d]:
                row = arrs.loc[idx]
                usado_dem = float(row[col_usado])
                nuevo_dem = float(row[col_nuevo])
                stock_usado += usado_dem + nuevo_dem

        # 3) Ventas que se van hoy (consumo definitivo de nuevo)
        if d in ventas_by_date.index:
            q_vta = float(ventas_by_date.loc[d])
            stock_nuevo -= q_vta

        # 4) Arriendos que comienzan hoy (descuentan stock)
        if d in arrs_start.index:
            usado_dem = float(arrs_start.loc[d, col_usado])
            nuevo_dem = float(arrs_start.loc[d, col_nuevo])
            stock_usado -= usado_dem
            stock_nuevo -= nuevo_dem

        registros.append({"Fecha": d, "nuevo": stock_nuevo, "usado": stock_usado, "total": stock_nuevo + stock_usado})

    stock_out = pd.DataFrame(registros).set_index("Fecha").sort_index()

    # Uso diario por proyecto (solo arriendos, usado+nuevo)
    if arrs.empty:
        uso_proj = pd.DataFrame()
    else:
        start_min = arrs["Inicio_norm"].min()
        end_max = arrs["Termino_norm"].max()
        idx_dates = pd.date_range(start_min, end_max, freq="D")
        proyectos = sorted(arrs["Proyecto"].unique())
        uso_proj = pd.DataFrame(0.0, index=idx_dates, columns=proyectos)

        for _, row in arrs.iterrows():
            ini = row["Inicio_norm"]
            fin = row["Termino_norm"]
            if pd.isna(ini) or pd.isna(fin):
                continue
            mask = (uso_proj.index >= ini) & (uso_proj.index < fin)
            total_pzas = float(row[col_usado]) + float(row[col_nuevo])
            uso_proj.loc[mask, row["Proyecto"]] += total_pzas

    alertas = stock_out[stock_out["total"] < 0].copy() if not stock_out.empty else pd.DataFrame()
    if not alertas.empty:
        alertas["deficit"] = -alertas["total"]

    return stock_out, uso_proj, alertas


def step_line_chart(df: pd.DataFrame, cols, y_title="Piezas", height=260):
    """Gráfico escalonado con hover (igual app anterior)."""
    if df is None or df.empty:
        return

    wide = df.copy()
    idx_name = wide.index.name or "Fecha"
    wide = wide.reset_index().rename(columns={idx_name: "Fecha"})
    wide["Fecha"] = pd.to_datetime(wide["Fecha"], errors="coerce")
    wide = wide.dropna(subset=["Fecha"]).sort_values("Fecha")

    long = wide.melt(id_vars="Fecha", value_vars=list(cols), var_name="Serie", value_name="Valor")
    long["Valor"] = pd.to_numeric(long["Valor"], errors="coerce").fillna(0)

    series_domain = list(cols)
    color_series = alt.Color("Serie:N", scale=alt.Scale(domain=series_domain), legend=None)
    nearest = alt.selection_point(nearest=True, on="mouseover", fields=["Fecha"], empty=False)

    lines_chart = (
        alt.Chart(long)
        .mark_line(interpolate="step-after")
        .encode(
            x=alt.X("Fecha:T", title="Fecha"),
            y=alt.Y("Valor:Q", title=y_title),
            color=color_series,
        )
    )

    selectors = alt.Chart(wide).mark_point(opacity=0).encode(x="Fecha:T").add_params(nearest)
    rule = alt.Chart(wide).mark_rule().encode(x="Fecha:T").transform_filter(nearest)

    points = (
        alt.Chart(long)
        .mark_point()
        .encode(
            x="Fecha:T",
            y="Valor:Q",
            color=color_series,
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
        )
        .transform_filter(nearest)
    )

    zero_line = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeWidth=3, color="black").encode(y="y:Q")

    main = alt.layer(lines_chart, selectors, points, rule, zero_line).properties(height=height).interactive()

    panel_h = max(120, int(height) + 40)

    detail_base = (
        alt.Chart(long)
        .transform_filter(nearest)
        .transform_window(row="row_number()", sort=[alt.SortField("Serie", order="ascending")])
        .transform_calculate(
            ypos="datum.row * 18 + 38",
            label="datum.Serie + ': ' + format(datum.Valor, '.0f')",
        )
    )

    detail_dots = detail_base.mark_point(filled=True, size=80).encode(
        x=alt.value(0),
        y=alt.Y("ypos:Q", axis=None, scale=alt.Scale(domain=[0, panel_h], range=[0, panel_h])),
        color=alt.Color("Serie:N", scale=alt.Scale(domain=series_domain), legend=None),
    )

    detail_text = detail_base.mark_text(align="left", dx=10).encode(
        x=alt.value(0),
        y=alt.Y("ypos:Q", axis=None, scale=alt.Scale(domain=[0, panel_h], range=[0, panel_h])),
        text="label:N",
        color=alt.Color("Serie:N", scale=alt.Scale(domain=series_domain), legend=None),
    )

    date_header = (
        alt.Chart(wide)
        .transform_filter(nearest)
        .transform_calculate(fecha_txt="timeFormat(datum.Fecha, '%d-%b-%Y')")
        .mark_text(align="left", fontWeight="bold")
        .encode(x=alt.value(0), y=alt.value(18), text="fecha_txt:N")
    )

    panel = alt.layer(date_header, detail_dots, detail_text).properties(width="container", height=panel_h)
    final = alt.vconcat(main.properties(width="container"), panel).configure_concat(spacing=8)

    st.altair_chart(final, use_container_width=True)


def uso_en_obra_chart(uso_wide: pd.DataFrame, *, title: str, height: int = 280):
    """Área apilada por obra + línea Total (igual app anterior)."""
    if uso_wide is None or uso_wide.empty:
        return None

    df = uso_wide.copy()
    if "Fecha" not in df.columns:
        idx_name = df.index.name or "Fecha"
        df = df.reset_index().rename(columns={idx_name: "Fecha", "index": "Fecha"})

    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"]).sort_values("Fecha")

    proj_cols = [c for c in df.columns if c != "Fecha"]
    for c in proj_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["Total"] = df[proj_cols].sum(axis=1) if proj_cols else 0
    df["HasUse"] = (df[proj_cols] > 0).sum(axis=1) if proj_cols else 0

    long = df.melt(id_vars=["Fecha"], value_vars=proj_cols, var_name="Proyecto", value_name="piezas")
    long["piezas"] = pd.to_numeric(long["piezas"], errors="coerce").fillna(0)

    nearest = alt.selection_point(nearest=True, on="mouseover", fields=["Fecha"], empty=False)

    proj_domain = sorted(long["Proyecto"].unique()) if not long.empty else []
    color_proj = alt.Color("Proyecto:N", title="Obra", scale=alt.Scale(domain=proj_domain))

    area = (
        alt.Chart(long)
        .mark_area(interpolate="step-after")
        .encode(
            x=alt.X("Fecha:T", title="Fecha"),
            y=alt.Y("piezas:Q", stack="zero", title="Piezas"),
            color=color_proj,
        )
    )

    total_line = (
        alt.Chart(df)
        .mark_line(interpolate="step-after", strokeWidth=3, color="black")
        .encode(x="Fecha:T", y=alt.Y("Total:Q", title="Piezas"))
    )

    selectors = alt.Chart(df).mark_point(opacity=0).encode(x="Fecha:T").add_params(nearest)
    rule = alt.Chart(df).mark_rule().encode(x="Fecha:T").transform_filter(nearest)

    main = alt.layer(area, total_line, selectors, rule).properties(height=height).interactive()

    panel_h = max(120, int(height) + 40)

    detail_base = (
        alt.Chart(long)
        .transform_filter(nearest)
        .transform_filter("datum.piezas > 0")
        .transform_window(row="row_number()", sort=[alt.SortField("piezas", order="descending")])
        .transform_calculate(
            ypos="datum.row * 18 + 78",
            label="datum.Proyecto + ': ' + format(datum.piezas, '.0f')",
        )
    )

    detail_dots = detail_base.mark_point(filled=True, size=80).encode(
        x=alt.value(0),
        y=alt.Y("ypos:Q", axis=None, scale=alt.Scale(domain=[0, panel_h], range=[0, panel_h])),
        color=alt.Color("Proyecto:N", scale=alt.Scale(domain=proj_domain), legend=None),
    )

    detail_text = detail_base.mark_text(align="left", dx=10).encode(
        x=alt.value(0),
        y=alt.Y("ypos:Q", axis=None, scale=alt.Scale(domain=[0, panel_h], range=[0, panel_h])),
        text="label:N",
        color=alt.Color("Proyecto:N", scale=alt.Scale(domain=proj_domain), legend=None),
    )

    date_header = (
        alt.Chart(df)
        .transform_filter(nearest)
        .transform_calculate(fecha_txt="timeFormat(datum.Fecha, '%d-%b-%Y')")
        .mark_text(align="left", fontWeight="bold")
        .encode(x=alt.value(0), y=alt.value(18), text="fecha_txt:N")
    )

    total_header = (
        alt.Chart(df)
        .transform_filter(nearest)
        .transform_calculate(total_txt="'Total: ' + format(datum.Total, '.0f')")
        .mark_text(align="left")
        .encode(x=alt.value(0), y=alt.value(38), text="total_txt:N")
    )

    no_use = (
        alt.Chart(df)
        .transform_filter(nearest)
        .transform_filter("datum.HasUse == 0")
        .mark_text(align="left")
        .encode(x=alt.value(0), y=alt.value(78), text=alt.value("Sin uso (>0)"))
    )

    panel = alt.layer(date_header, total_header, no_use, detail_dots, detail_text).properties(width="container", height=panel_h)
    final = alt.vconcat(main.properties(width="container"), panel).properties(title=title).configure_concat(spacing=8)
    return final


def disponibilidad_tab(stock: pd.DataFrame, proyectos: pd.DataFrame):
    st.header("📦 Disponibilidad")

    stock_c = _clean_stock_dispo_v2(stock)
    obras_c = _obras_from_proyectos_v2(proyectos)

    # -------- WF
    st.subheader("WF600x2250 – Stock (Nuevo / Usado / Total)")
    stock_wf, uso_wf, alertas_wf = _simular_pieza(stock_c, obras_c, "WF600x2250")
    if stock_wf is not None and not stock_wf.empty:
        step_line_chart(stock_wf, ["nuevo", "usado", "total"], y_title="Piezas", height=260)

    st.subheader("WF600x2250 – Uso en obra (Arriendos) + Total")
    if uso_wf is not None and not uso_wf.empty:
        uso_wf_wide = uso_wf.reset_index().rename(columns={"index": "Fecha"})
        chart = uso_en_obra_chart(uso_wf_wide, title="Uso WF600x2250", height=280)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No hay uso en obra (arriendos) para WF600x2250.")

    st.divider()

    # -------- CE
    st.subheader("CE600x1200 – Stock (Nuevo / Usado / Total)")
    stock_ce, uso_ce, alertas_ce = _simular_pieza(stock_c, obras_c, "CE600x1200")
    if stock_ce is not None and not stock_ce.empty:
        step_line_chart(stock_ce, ["nuevo", "usado", "total"], y_title="Piezas", height=260)

    st.subheader("CE600x1200 – Uso en obra (Arriendos) + Total")
    if uso_ce is not None and not uso_ce.empty:
        uso_ce_wide = uso_ce.reset_index().rename(columns={"index": "Fecha"})
        chart = uso_en_obra_chart(uso_ce_wide, title="Uso CE600x1200", height=280)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No hay uso en obra (arriendos) para CE600x1200.")



# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Parámetros")

HOY = pd.to_datetime(
    st.sidebar.date_input("Fecha base", value=pd.Timestamp.today())
)

ritmo_taller = st.sidebar.number_input("Ritmo base Taller", value=70.0)
ritmo_lavado = st.sidebar.number_input("Ritmo base Lavado", value=100.0)

autosave = st.sidebar.checkbox("Guardar automáticamente en Excel", value=True)

if st.sidebar.button("💾 Guardar ahora"):
    save_all_data(st.session_state["df_proy"], st.session_state["df_stock"], st.session_state["df_lav"])
    st.sidebar.success("Guardado en proyectos_v2.xlsx ✅")


# ============================================================
# CARGA DATOS (SESSION_STATE)
# ============================================================

if "df_proy" not in st.session_state:
    proy, stock, lav = load_all_data()
    st.session_state["df_proy"] = schema_proyectos_keep_rowid(proy)
    st.session_state["df_stock"] = schema_stock_keep_rowid(stock)
    st.session_state["df_lav"] = schema_lavado_keep_rowid(lav)
else:
    # Por si venía de versión antigua sin __rowid
    st.session_state["df_proy"] = schema_proyectos_keep_rowid(st.session_state["df_proy"])
    st.session_state["df_stock"] = schema_stock_keep_rowid(st.session_state["df_stock"])
    st.session_state["df_lav"] = schema_lavado_keep_rowid(st.session_state["df_lav"])


df_proy = st.session_state["df_proy"]
df_stock = st.session_state["df_stock"]
df_lav = st.session_state["df_lav"]



# ============================================================
# TABS
# ============================================================

tabs = st.tabs(["📚 Datos", "🧰 Taller", "🧽 Lavado", "📦 Disponibilidad"])


# ================= DATOS =================
with tabs[0]:
    st.header("Datos")

    st.subheader("Proyectos")
    proy_cfg = {
        "Proyecto": st.column_config.TextColumn("Proyecto", width="medium"),
        "Constructora": st.column_config.TextColumn("Const.", width="small"),
        "Tipo": st.column_config.SelectboxColumn(
            "Tipo",
            options=["Venta", "Arriendo", "Arriendo MO", "Reparación"],
            required=True,
            width="small",
        ),
        "Fecha_requerida": st.column_config.DateColumn("F. Req", width="small"),
        "Inicio_obra": st.column_config.DateColumn("Inicio_obra", width="small"),
        "Duracion_obra_meses": st.column_config.NumberColumn("Duración", width="small"),
        "Termino_obra": st.column_config.DateColumn("Término_obra", disabled=True, width="small"),
    
        "M2": st.column_config.NumberColumn("M2", width="small"),
        "Avance_pct": st.column_config.NumberColumn("Av %", min_value=0, max_value=100, step=1, width="small"),
        "Avance_m2": st.column_config.NumberColumn("Av m²", disabled=True, width="small"),
        "Ritmo_esperado": st.column_config.NumberColumn("Ritmo", width="small"),
    
        "WF600x2250_usado": st.column_config.NumberColumn("WF U", width="small"),
        "WF600x2250_nuevo": st.column_config.NumberColumn("WF N", width="small"),
        "CE600x1200_usado": st.column_config.NumberColumn("CE U", width="small"),
        "CE600x1200_nuevo": st.column_config.NumberColumn("CE N", width="small"),
    
        "Comentario": st.column_config.TextColumn("Comentario", width="medium"),
    }

    df_proy = stable_data_editor(
        df_key="df_proy",
        widget_key="editor_proyectos_v2_fix",
        column_config=proy_cfg,
        schema_fn=schema_proyectos_keep_rowid,
        view_df=st.session_state["df_proy"],
        height=_df_height(st.session_state["df_proy"]),
        num_rows="dynamic",
    )

    st.subheader("Stock")
    stock_cfg = {"Fecha": st.column_config.DateColumn("Fecha")}
    df_stock = stable_data_editor(
        df_key="df_stock",
        widget_key="editor_stock_v2_fix",
        column_config=stock_cfg,
        schema_fn=schema_stock_keep_rowid,
        view_df=st.session_state["df_stock"],
        height=_df_height(st.session_state["df_stock"]),
        num_rows="dynamic",
    )

    st.subheader("Lavado")
    lav_cfg = {
        "Fecha Requerida": st.column_config.DateColumn("Fecha requerida"),
        "Inicio": st.column_config.DateColumn("Inicio"),
        "Termino": st.column_config.DateColumn("Término"),
        "Inicio_prog": st.column_config.DateColumn("Inicio programado"),
        "Comentario": st.column_config.TextColumn("Comentario"),
    }
    df_lav = stable_data_editor(
        df_key="df_lav",
        widget_key="editor_lavado_v2_fix",
        column_config=lav_cfg,
        schema_fn=schema_lavado_keep_rowid,
        view_df=st.session_state["df_lav"],
        height=_df_height(st.session_state["df_lav"]),
        num_rows="dynamic",
    )

    # Guardado automático (ya con df canónico actualizado a la primera)
    if autosave:
        save_all_data(
            drop_internal_cols(st.session_state["df_proy"]),
            drop_internal_cols(st.session_state["df_stock"]),
            drop_internal_cols(st.session_state["df_lav"]),
        )


# ================= TALLER =================
with tabs[1]:
    st.header("Taller")
    df_proy_now = drop_internal_cols(st.session_state["df_proy"]).copy()

    base = df_proy_now.copy()
    base["Avance"] = base["Avance_pct"]
    base["Ritmo"] = base["Ritmo_esperado"]
    base["Fecha Requerida"] = base["Fecha_requerida"]

    res = programa_linea(base, ritmo_taller, HOY)
    st.dataframe(res, height=_df_height(res))

    export_block(res, name="Taller calculado", key_prefix="taller_calculado")


# ================= LAVADO =================
with tabs[2]:
    st.header("Lavado")

    df_lav_now = st.session_state["df_lav"].copy()
    res_lav = programa_linea(df_lav_now, ritmo_lavado, HOY)

    st.dataframe(res_lav, height=_df_height(res_lav))

    export_block(res_lav, name="Lavado calculado", key_prefix="lavado_calculado")

# ================= DISPONIBILIDAD =================
with tabs[3]:
    df_stock_now = st.session_state["df_stock"].copy()
    df_proy_now = st.session_state["df_proy"].copy()
    disponibilidad_tab(df_stock_now, df_proy_now)



