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

import requests
import base64
import os
import tempfile
import time
import json
import hashlib

st.set_page_config(page_title="Proyectos V2", layout="wide", initial_sidebar_state="collapsed")

# version deploy 2026-05
# --- CONFIG GITHUB ---
GITHUB_TOKEN = st.secrets["github"]["token"]  # lo pones en secrets.toml
REPO_OWNER = "c-izquierdo"
REPO_NAME = "Produccion"
FILE_PATH_GITHUB = "proyectos_v2.xlsx"  # ruta dentro del repo
BRANCH = "main"

def load_from_github():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH_GITHUB}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"])

        temp_path = "temp_load.xlsx"
        with open(temp_path, "wb") as f:
            f.write(content)

        return pd.read_excel(temp_path, sheet_name=None)

    return None

def save_to_github(local_file_path, commit_message="update proyectos desde streamlit"):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH_GITHUB}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    with open(local_file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code == 404:
        sha = None
    else:
        return False, f"No se pudo obtener SHA actual (HTTP {r.status_code}): {r.text}"

    data = {
        "message": commit_message,
        "content": content,
        "branch": BRANCH,
    }
    if sha:
        data["sha"] = sha

    response = requests.put(url, headers=headers, json=data, timeout=30)
    if response.status_code in (200, 201):
        new_sha = response.json().get("content", {}).get("sha", "")
        return True, new_sha

    return False, f"Error subiendo a GitHub (HTTP {response.status_code}): {response.text}"


def notify(message: str, success: bool = True):
    try:
        st.toast(message, icon="✅" if success else "❌")
    except Exception:
        if success:
            st.success(message)
        else:
            st.error(message)


def export_current_state_to_excel(local_file_path: str):
    proy = normalizar_proyectos(st.session_state["df_proy"].copy())
    stock = normalizar_stock(st.session_state["df_stock"].copy())
    lav = normalizar_lavado(st.session_state["df_lav"].copy())

    with pd.ExcelWriter(local_file_path, engine="openpyxl") as writer:
        drop_internal_cols(proy).to_excel(writer, sheet_name="proyectos", index=False)
        drop_internal_cols(stock).to_excel(writer, sheet_name="stock_dispo", index=False)
        drop_internal_cols(lav).to_excel(writer, sheet_name="lavado", index=False)


def _df_signature(df: pd.DataFrame) -> str:
    if df is None:
        return "none"

    tmp = df.copy()
    for c in tmp.columns:
        if pd.api.types.is_datetime64_any_dtype(tmp[c]) or pd.api.types.is_object_dtype(tmp[c]):
            tmp[c] = tmp[c].astype(str)
    tmp = tmp.fillna("")
    payload = tmp.to_json(orient="split", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_state_signature() -> str:
    parts = [
        _df_signature(st.session_state.get("df_proy")),
        _df_signature(st.session_state.get("df_stock")),
        _df_signature(st.session_state.get("df_lav")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def immediate_autosave(reason: str = "cambio"):
    if not st.session_state.get("autosave_enabled", True):
        return False

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp_path = tmp.name
        export_current_state_to_excel(tmp_path)

        ok, detail = save_to_github(
            tmp_path,
            commit_message=f"{reason}: update automático desde streamlit"
        )

        if ok:
            st.session_state["last_saved_signature"] = current_state_signature()
            st.session_state["last_save_ok"] = True
            st.session_state["last_save_detail"] = detail
            st.session_state["last_save_ts"] = time.time()
            notify("💾 Guardado en GitHub", success=True)
            return True

        notify(f"⚠️ Error al guardar: {detail}", success=False)
        st.session_state["last_save_ok"] = False
        st.session_state["last_save_detail"] = detail
        return False
    except Exception as e:
        notify(f"❌ Error en autosave: {str(e)}", success=False)
        st.session_state["last_save_ok"] = False
        st.session_state["last_save_detail"] = str(e)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def autosave_if_needed():
    if not st.session_state.get("autosave_enabled", True):
        return

    current_sig = current_state_signature()
    last_sig = st.session_state.get("last_saved_signature")
    if last_sig is None:
        st.session_state["last_saved_signature"] = current_sig
        return

    if current_sig == last_sig:
        return

    if st.session_state.get("_autosave_lock", False):
        return

    st.session_state["_autosave_lock"] = True
    try:
        immediate_autosave(reason="autosave")
    finally:
        st.session_state["_autosave_lock"] = False


def check_password():
    def password_entered():
        if st.session_state.get("password") == st.secrets["auth"]["password"]:
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        return False

    if not st.session_state["authenticated"]: 
        st.title("Acceso a Plataforma")
        st.caption("Ingrese la contraseña para continuar")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        st.error("Contraseña incorrecta")
        return False

    return True


if not check_password():
    st.stop()

# ============================================================
# CONFIG
# ============================================================

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

/* -------------------------- */
/* Ocultar sidebar por defecto */
section[data-testid="stSidebar"]{
    transform: translateX(calc(-1 * var(--sidebar-open-w))) !important;
    transition: transform .28s ease-in-out !important;
}
section[data-testid="stSidebar"][aria-expanded="true"]{
    transform: translateX(0) !important;
}
</style>
""",
    unsafe_allow_html=True
)

# Botón HTML/JS para alternar el sidebar (inicialmente escondido)
components.html(
        """
        <script>
            // Intentar establecer el sidebar oculto al inicio (reintentar si no existe aún)
            (function init(){
                function ensureSidebar(){
                    return document.querySelector('section[data-testid="stSidebar"]');
                }
                function setSidebarState(exp){
                    const s = ensureSidebar();
                    if(!s) return;
                    s.setAttribute('aria-expanded', exp ? 'true' : 'false');
                }

                let tries = 0;
                const t = setInterval(()=>{
                    const s = ensureSidebar();
                    tries += 1;
                    if(s){
                        setSidebarState(false);
                        clearInterval(t);
                    }
                    if(tries>30) clearInterval(t);
                }, 100);
            })();
        </script>
        """,
        height=1,
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
    """Devuelve un bloque monoespaciado para pegar en Teams sin desorden."""
    body = df_to_pretty_text(df)
    return f"```\n{body}\n```"


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

def df_to_pretty_text(df: pd.DataFrame) -> str:
    """Texto alineado para TXT (ideal para Teams o archivos de texto)."""
    if df is None or df.empty:
        return "(sin datos)"
    try:
        from tabulate import tabulate
        return tabulate(df, headers="keys", tablefmt="psql", showindex=False)
    except Exception:
        # Fallback estable: TSV
        return df.to_csv(sep="\t", index=False)

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

def ensure_rowid(df: pd.DataFrame, col: str = ROWID_COL) -> pd.DataFrame:
    """Asegura __rowid no nulo, único y estable."""
    df = df.copy()
    if col not in df.columns:
        df[col] = [uuid.uuid4().hex for _ in range(len(df))]
    else:
        df[col] = df[col].astype(str)

    mask = df[col].isna() | (df[col].str.strip() == "") | (df[col].str.lower() == "nan")
    if mask.any():
        df.loc[mask, col] = [uuid.uuid4().hex for _ in range(int(mask.sum()))]

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

    # __rowid al final
    cols = [c for c in df.columns if c != col] + [col]
    return df[cols]

def drop_internal_cols(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in df.columns if c.startswith("__")], errors="ignore")

def _apply_editor_delta(df_key: str, widget_key: str, schema_fn):
    """Aplica delta (edited/deleted/added) del data_editor a la tabla base en session_state."""
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

        # ✅ Asegura Avance_pct para que una fila nueva no quede filtrada por accidente
        if "Avance_pct" in base_i.columns and "Avance_pct" not in new_df.columns:
            new_df["Avance_pct"] = 0
        if "Avance_pct" in new_df.columns:
            new_df["Avance_pct"] = pd.to_numeric(new_df["Avance_pct"], errors="coerce").fillna(0)

        new_df = ensure_rowid(new_df)

        # Alinea columnas a base
        for c in base_i.columns:
            if c not in new_df.columns:
                new_df[c] = np.nan
        new_df = new_df[base_i.columns]

        base_i = pd.concat([base_i, new_df], axis=0)

    # 4) ✅ MUY IMPORTANTE: guardar de vuelta en session_state (y aplicar schema)
    out = base_i.reset_index(drop=True)
    out = schema_fn(out) if schema_fn is not None else ensure_rowid(out)
    st.session_state[df_key] = out

    if edited_rows or deleted_rows or added_rows:
        immediate_autosave(reason="edición")


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
    """Editor estable: permite editar/agregar/borrar incluso con view_df filtrada, usando __rowid."""
    if df_key not in st.session_state:
        st.session_state[df_key] = pd.DataFrame()

    st.session_state[df_key] = ensure_rowid(st.session_state[df_key])

    df_base = st.session_state[df_key]
    view_df = df_base if view_df is None else view_df
    view_df = ensure_rowid(view_df)

    editor_df = view_df.copy()
    if ROWID_COL in editor_df.columns:
        editor_df = editor_df[[c for c in editor_df.columns if c != ROWID_COL] + [ROWID_COL]]

    # Mapa de filas visibles -> __rowid
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

def add_bdays(start, n):
    """Suma n días hábiles (L-V). Mantiene la semántica de +Timedelta(days=n) pero sin fines de semana."""
    start_ts = pd.Timestamp(start).normalize()
    n = int(n)
    if n <= 0:
        return start_ts
    # np.busday_offset: cuenta solo L-V (no considera festivos; si lo necesitas se puede extender)
    d = np.busday_offset(start_ts.date(), n, roll="forward")
    return pd.Timestamp(d).normalize()

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
        fin = add_bdays(inicio, max(0, dias))

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


def _simular_pieza(stock_df: pd.DataFrame, obras_df: pd.DataFrame, pieza_prefix: str, return_events: bool = False):
    """
    Simula stock nuevo/usado/total en el tiempo.

    Para VENTA: descuenta NUEVO desde Inicio_obra (no vuelve).
    Para ARRIENDO: descuenta durante la obra y devuelve TODO como USADO al término.

    NUEVO (opcional):
    - Si return_events=True, devuelve además un DataFrame 'eventos_df' con:
      Fecha, Proyecto, Tipo_evento, Cambio, usado, nuevo
    """
    col_usado = f"{pieza_prefix}_usado"
    col_nuevo = f"{pieza_prefix}_nuevo"

    stock = stock_df.copy()
    if stock.empty:
        if return_events:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    obras = obras_df.copy()
    obras = obras[~obras["Inicio_obra"].isna()].copy()

    ventas = obras[obras["Tipo"].str.upper() == "VENTA"].copy()
    arrs = obras[(obras["Tipo"].str.upper() == "ARRIENDO") & (~obras["Termino_obra"].isna())].copy()

    # --- Eventos (para identificar qué proyecto provoca cambios por fecha) ---
    eventos = []

    # Fechas relevantes
    fechas_evt = set(stock["Fecha"].dt.normalize())
    fechas_evt.update(ventas["Inicio_obra"].dt.normalize())
    fechas_evt.update(arrs["Inicio_obra"].dt.normalize())
    fechas_evt.update(arrs["Termino_obra"].dt.normalize())

    if not fechas_evt:
        if return_events:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    fechas = sorted(fechas_evt)

    # Agregados por fecha
    stock_by_date = (
        stock.groupby(stock["Fecha"].dt.normalize())[[f"{pieza_prefix}_nuevo", f"{pieza_prefix}_usado"]]
        .sum()
    )

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
            inc_nuevo = float(stock_by_date.loc[d, f"{pieza_prefix}_nuevo"])
            inc_usado = float(stock_by_date.loc[d, f"{pieza_prefix}_usado"])
            stock_nuevo += inc_nuevo
            stock_usado += inc_usado

            if (inc_nuevo != 0) or (inc_usado != 0):
                eventos.append({
                    "Fecha": d,
                    "Proyecto": "(Stock)",
                    "Tipo_evento": "Entrada stock",
                    "Cambio": inc_nuevo + inc_usado,
                    "nuevo": inc_nuevo,
                    "usado": inc_usado,
                })

        # 2) Devolución arriendos que terminan hoy (todo vuelve como usado)
        if d in terminos_map:
            for idx in terminos_map[d]:
                row = arrs.loc[idx]
                usado_dem = float(row[col_usado])
                nuevo_dem = float(row[col_nuevo])

                stock_usado += usado_dem + nuevo_dem

                cambio_total = (usado_dem + nuevo_dem)
                if cambio_total != 0:
                    eventos.append({
                        "Fecha": d,
                        "Proyecto": row.get("Proyecto", ""),
                        "Tipo_evento": "Término obra (Devolución)",
                        "Cambio": cambio_total,
                        "nuevo": 0.0,
                        "usado": cambio_total,
                    })

        # 3) Ventas que se van hoy (consumo definitivo de nuevo)
        if d in ventas_by_date.index:
            q_vta = float(ventas_by_date.loc[d])
            stock_nuevo -= q_vta

            ventas_hoy = ventas[ventas["Inicio_obra"].dt.normalize() == d]
            if not ventas_hoy.empty:
                for _, r in ventas_hoy.iterrows():
                    q = float(r.get(col_nuevo, 0) if pd.notna(r.get(col_nuevo, 0)) else 0)
                    if q != 0:
                        eventos.append({
                            "Fecha": d,
                            "Proyecto": r.get("Proyecto", ""),
                            "Tipo_evento": "Venta",
                            "Cambio": -q,
                            "nuevo": -q,
                            "usado": 0.0,
                        })
            else:
                if q_vta != 0:
                    eventos.append({
                        "Fecha": d,
                        "Proyecto": "(Venta)",
                        "Tipo_evento": "Venta",
                        "Cambio": -q_vta,
                        "nuevo": -q_vta,
                        "usado": 0.0,
                    })

        # 4) Arriendos que comienzan hoy (descuentan stock)
        if d in arrs_start.index:
            usado_dem = float(arrs_start.loc[d, col_usado])
            nuevo_dem = float(arrs_start.loc[d, col_nuevo])
            stock_usado -= usado_dem
            stock_nuevo -= nuevo_dem

            arrs_hoy = arrs[arrs["Inicio_norm"] == d]
            if not arrs_hoy.empty:
                for _, r in arrs_hoy.iterrows():
                    u = float(r.get(col_usado, 0) if pd.notna(r.get(col_usado, 0)) else 0)
                    n = float(r.get(col_nuevo, 0) if pd.notna(r.get(col_nuevo, 0)) else 0)
                    tot = u + n
                    if tot != 0:
                        eventos.append({
                            "Fecha": d,
                            "Proyecto": r.get("Proyecto", ""),
                            "Tipo_evento": "Inicio obra (Arriendo)",
                            "Cambio": -tot,
                            "nuevo": -n,
                            "usado": -u,
                        })
            else:
                tot = usado_dem + nuevo_dem
                if tot != 0:
                    eventos.append({
                        "Fecha": d,
                        "Proyecto": "(Arriendo)",
                        "Tipo_evento": "Inicio obra (Arriendo)",
                        "Cambio": -tot,
                        "nuevo": -nuevo_dem,
                        "usado": -usado_dem,
                    })

        registros.append({
            "Fecha": d,
            "nuevo": stock_nuevo,
            "usado": stock_usado,
            "total": stock_nuevo + stock_usado
        })

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

    eventos_df = pd.DataFrame(eventos)
    if not eventos_df.empty:
        eventos_df["Fecha"] = pd.to_datetime(eventos_df["Fecha"], errors="coerce").dt.normalize()
        eventos_df["Cambio"] = pd.to_numeric(eventos_df["Cambio"], errors="coerce").fillna(0)

    if return_events:
        return stock_out, uso_proj, alertas, eventos_df
    return stock_out, uso_proj, alertas


def step_line_chart(df: pd.DataFrame, cols, y_title="Piezas", height=260, eventos_df=None):
    """Gráfico escalonado con hover + panel detalle. Ahora incluye eventos (proyecto responsable) si eventos_df está presente."""
    if df is None or df.empty:
        return

    # ---- Base (wide) ----
    wide = df.copy()
    idx_name = wide.index.name or "Fecha"
    wide = wide.reset_index().rename(columns={idx_name: "Fecha"})
    wide["Fecha"] = pd.to_datetime(wide["Fecha"], errors="coerce").dt.normalize()
    wide = wide.dropna(subset=["Fecha"]).sort_values("Fecha")

    # ---- Preparar eventos (si vienen) ----
    ev = None
    ev_dates = None
    if eventos_df is not None and isinstance(eventos_df, pd.DataFrame) and not eventos_df.empty:
        ev = eventos_df.copy()
        ev["Fecha"] = pd.to_datetime(ev["Fecha"], errors="coerce").dt.normalize()
        ev = ev.dropna(subset=["Fecha"]).copy()
        ev["Cambio"] = pd.to_numeric(ev.get("Cambio", 0), errors="coerce").fillna(0)

        # Conteo eventos por fecha (para mostrar "Sin eventos")
        ev_dates = ev.groupby("Fecha").size().reset_index(name="n_events")

        # Etiqueta bonita
        def _fmt_signed(x):
            try:
                x = float(x)
            except Exception:
                x = 0.0
            return f"{x:+.0f}"

        ev["Cambio_txt"] = ev["Cambio"].apply(_fmt_signed)
        ev["label"] = (
            ev["Proyecto"].astype(str)
            + " — "
            + ev["Tipo_evento"].astype(str)
            + " ("
            + ev["Cambio_txt"].astype(str)
            + ")"
        )

    # Enriquecer wide con n_events para poder mostrar "Sin eventos"
    wide2 = wide.copy()
    # --- asegurar columna n_events SIEMPRE ---
    wide2["n_events"] = 0
    
    if ev_dates is not None and not ev_dates.empty:
        wide2 = wide2.merge(ev_dates, on="Fecha", how="left")
        if "n_events" in wide2.columns:
            wide2["n_events"] = (
                pd.to_numeric(wide2["n_events"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        else:
            wide2["n_events"] = 0


    # ---- long para líneas ----
    long = wide2.melt(id_vars="Fecha", value_vars=list(cols), var_name="Serie", value_name="Valor")
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

    selectors = alt.Chart(wide2).mark_point(opacity=0).encode(x="Fecha:T").add_params(nearest)
    rule = alt.Chart(wide2).mark_rule().encode(x="Fecha:T").transform_filter(nearest)

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

    main_layers = [lines_chart, selectors, points, rule, zero_line]
    main = alt.layer(*main_layers).properties(height=height).interactive()

    # ---- Panel detalle (series) ----
    panel_h = max(140, int(height) + 80)

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
        alt.Chart(wide2)
        .transform_filter(nearest)
        .transform_calculate(fecha_txt="timeFormat(datum.Fecha, '%d-%b-%Y')")
        .mark_text(align="left", fontWeight="bold")
        .encode(x=alt.value(0), y=alt.value(18), text="fecha_txt:N")
    )

    # ---- Panel eventos (proyecto responsable) ----
    ev_header = alt.Chart(pd.DataFrame({"txt": ["Eventos:"]})).mark_text(
        align="left", fontWeight="bold"
    ).encode(
        x=alt.value(0),
        y=alt.value(130),  # 👈 baja el título
        text="txt:N"
    )

    ev_text = None
    no_ev_text = None

    if ev is not None and not ev.empty:
        ev_text = (
            alt.Chart(ev)
            .transform_filter(nearest)
            .transform_window(row="row_number()", sort=[alt.SortField("Tipo_evento", order="ascending")])
            .transform_calculate(ypos="datum.row * 18 + 150")
            .mark_text(align="left")
            .encode(
                x=alt.value(0),
                y=alt.Y("ypos:Q", axis=None, scale=alt.Scale(domain=[0, panel_h], range=[0, panel_h])),
                text="label:N",
            )
        )
    else:
        # Si no se pasan eventos_df, mostramos una nota suave
        no_ev_text = (
            alt.Chart(pd.DataFrame({"txt": ["(sin eventos: activa return_events=True)"]}))
            .mark_text(align="left", color="#6b7280")
            .encode(x=alt.value(0), y=alt.value(120), text="txt:N")
        )

    panel_layers = [date_header, detail_dots, detail_text, ev_header]
    if no_ev_text is not None:
        panel_layers.append(no_ev_text)
    if ev_text is not None:
        panel_layers.append(ev_text)

    panel = alt.layer(*panel_layers).properties(width="container", height=panel_h)

    final = alt.vconcat(
        main.properties(width="container"),
        panel
    ).configure_concat(spacing=8)

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
    stock_wf, uso_wf, alertas_wf, eventos_wf = _simular_pieza(stock_c, obras_c, "WF600x2250", return_events=True)

    if stock_wf is not None and not stock_wf.empty:
        step_line_chart(stock_wf, ["nuevo", "usado", "total"], y_title="Piezas", height=260, eventos_df=eventos_wf)

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
    stock_ce, uso_ce, alertas_ce, eventos_ce = _simular_pieza(stock_c, obras_c, "CE600x1200", return_events=True)

    if stock_ce is not None and not stock_ce.empty:
        step_line_chart(stock_ce, ["nuevo", "usado", "total"], y_title="Piezas", height=260, eventos_df=eventos_ce)

    st.subheader("CE600x1200 – Uso en obra (Arriendos) + Total")
    if uso_ce is not None and not uso_ce.empty:
        uso_ce_wide = uso_ce.reset_index().rename(columns={"index": "Fecha"})
        chart = uso_en_obra_chart(uso_ce_wide, title="Uso CE600x1200", height=280)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No hay uso en obra (arriendos) para CE600x1200.")


def alertas_calidad_informacion(df_proy: pd.DataFrame) -> pd.DataFrame:
    df = drop_internal_cols(df_proy.copy())
    df_act = df[pd.to_numeric(df.get("Avance_pct"), errors="coerce").fillna(0) < 100].copy()

    if df_act.empty:
        return pd.DataFrame(columns=["Proyecto", "Alerta", "Detalle", "Severidad"])

    alerta_rows = []
    for _, row in df_act.iterrows():
        proyecto = str(row.get("Proyecto", "")).strip()
        detalle = []

        fecha_req = pd.to_datetime(row.get("Fecha_requerida"), errors="coerce")
        inicio_obra = pd.to_datetime(row.get("Inicio_obra"), errors="coerce")
        tipo = str(row.get("Tipo", "")).strip()
        tipo_norm = tipo.upper()
        m2 = pd.to_numeric(row.get("M2"), errors="coerce")
        duracion = pd.to_numeric(row.get("Duracion_obra_meses"), errors="coerce")
        comentario = str(row.get("Comentario", "")).strip().lower()

        if pd.isna(fecha_req):
            detalle.append("Falta Fecha_requerida")
        if pd.isna(inicio_obra):
            detalle.append("Falta Inicio_obra")
        if pd.isna(m2) or m2 <= 0:
            detalle.append("M2 vacío o <= 0")
        if tipo == "":
            detalle.append("Falta Tipo")
        if tipo_norm in {"ARRIENDO", "ARRIENDO MO"} and pd.isna(duracion):
            detalle.append("Falta Duracion_obra_meses para arriendo")
        if "estimado" in comentario:
            detalle.append('Comentario contiene "estimado"')

        moldaje_cols = [
            "WF600x2250_usado",
            "WF600x2250_nuevo",
            "CE600x1200_usado",
            "CE600x1200_nuevo",
        ]
        moldaje_vals = [pd.to_numeric(row.get(c), errors="coerce") for c in moldaje_cols]
        if all(pd.isna(v) for v in moldaje_vals):
            detalle.append("Cantidades de moldaje WF / CE no informadas")

        if detalle:
            alerta_rows.append({
                "Proyecto": proyecto,
                "Alerta": "Calidad de información",
                "Detalle": "; ".join(detalle),
                "Severidad": "Media",
            })

    return pd.DataFrame(alerta_rows, columns=["Proyecto", "Alerta", "Detalle", "Severidad"])


def alertas_cumplimiento_inicio(df_proy: pd.DataFrame, df_stock: pd.DataFrame) -> pd.DataFrame:
    df = drop_internal_cols(df_proy.copy())
    df_act = df[pd.to_numeric(df.get("Avance_pct"), errors="coerce").fillna(0) < 100].copy()

    if df_act.empty:
        return pd.DataFrame(columns=["Proyecto", "Tipo", "Material", "Fecha inicio", "Déficit (pzas)", "Severidad"])

    obras = _obras_from_proyectos_v2(df_act)
    stock_c = _clean_stock_dispo_v2(df_stock.copy())
    alertas = []

    if obras.empty or stock_c.empty:
        return pd.DataFrame(columns=["Proyecto", "Tipo", "Material", "Fecha inicio", "Déficit (pzas)", "Severidad"])

    tipo_map = obras.set_index("Proyecto")["Tipo"].to_dict()

    for pieza_prefix, material in [("WF600x2250", "WF600x2250"), ("CE600x1200", "CE600x1200")]:
        stock_out, _, _, eventos = _simular_pieza(stock_c, obras, pieza_prefix, return_events=True)
        if stock_out is None or stock_out.empty or eventos is None or eventos.empty:
            continue

        eventos = eventos.copy()
        eventos["Fecha"] = pd.to_datetime(eventos["Fecha"], errors="coerce").dt.normalize()
        start_events = eventos[eventos["Tipo_evento"].isin(["Inicio obra (Arriendo)", "Venta"])].copy()
        if start_events.empty:
            continue

        start_events = start_events.reset_index(drop=True)
        start_events["demanda_usado"] = -start_events["usado"].fillna(0)
        start_events["demanda_nuevo"] = -start_events["nuevo"].fillna(0)

        for fecha, grupo in start_events.groupby("Fecha", sort=True):
            if fecha not in stock_out.index:
                continue

            final_usado = float(stock_out.loc[fecha, "usado"])
            final_nuevo = float(stock_out.loc[fecha, "nuevo"])
            total_demand_usado = float(grupo["demanda_usado"].sum())
            total_demand_nuevo = float(grupo["demanda_nuevo"].sum())

            before_any_start_usado = final_usado + total_demand_usado
            before_any_start_nuevo = final_nuevo + total_demand_nuevo
            running_usado = 0.0
            running_nuevo = 0.0

            for _, ev in grupo.iterrows():
                proyecto = str(ev.get("Proyecto", "")).strip()
                tipo = tipo_map.get(proyecto, "").upper()
                fecha_inicio = ev["Fecha"]

                if tipo not in {"VENTA", "ARRIENDO"}:
                    running_usado += float(ev["demanda_usado"])
                    running_nuevo += float(ev["demanda_nuevo"])
                    continue

                obra = obras[obras["Proyecto"] == proyecto]
                if obra.empty:
                    running_usado += float(ev["demanda_usado"])
                    running_nuevo += float(ev["demanda_nuevo"])
                    continue

                obra = obra.iloc[0]
                req_usado = pd.to_numeric(obra.get(f"{pieza_prefix}_usado"), errors="coerce")
                req_nuevo = pd.to_numeric(obra.get(f"{pieza_prefix}_nuevo"), errors="coerce")
                req_usado = float(req_usado if not pd.isna(req_usado) else 0.0)
                req_nuevo = float(req_nuevo if not pd.isna(req_nuevo) else 0.0)

                if tipo == "VENTA":
                    req = req_nuevo
                    available = before_any_start_nuevo - running_nuevo
                else:
                    req = req_usado + req_nuevo
                    available = before_any_start_usado - running_usado

                if req > 0 and available < req:
                    alertas.append({
                        "Proyecto": proyecto,
                        "Tipo": tipo,
                        "Material": material,
                        "Fecha inicio": fecha_inicio.date() if pd.notna(fecha_inicio) else "",
                        "Déficit (pzas)": round(req - max(available, 0.0), 2),
                        "Severidad": "Alta",
                    })

                running_usado += float(ev["demanda_usado"])
                running_nuevo += float(ev["demanda_nuevo"])

    return pd.DataFrame(alertas, columns=["Proyecto", "Tipo", "Material", "Fecha inicio", "Déficit (pzas)", "Severidad"])


def alertas_tab(df_proy: pd.DataFrame, df_stock: pd.DataFrame):
    st.header("🚨 Alertas Operativas")

    st.subheader("🟡 Calidad de la información")
    calidad = alertas_calidad_informacion(df_proy)
    if calidad.empty:
        st.success("✅ Todos los proyectos tienen información mínima completa.")
    else:
        st.warning("Existen proyectos con alertas de calidad de información.")
        st.dataframe(calidad)

    st.divider()
    st.subheader("🔴 Cumplimiento para inicio de proyectos")
    cumplimiento = alertas_cumplimiento_inicio(df_proy, df_stock)
    if cumplimiento.empty:
        st.success("✅ Todos los proyectos pueden comenzar según stock disponible.")
    else:
        st.error("Existen proyectos con déficit de stock para iniciar.")
        st.dataframe(cumplimiento)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Parámetros")

HOY = pd.to_datetime(
    st.sidebar.date_input("Fecha base", value=pd.Timestamp.today())
)

ritmo_taller = st.sidebar.number_input("Ritmo base Taller", value=80.0)
ritmo_lavado = st.sidebar.number_input("Ritmo base Lavado", value=100.0)

autosave = st.sidebar.checkbox("Guardar automáticamente en GitHub", value=True, help="Guarda los cambios automáticamente cada vez que edites los datos")
st.session_state["autosave_enabled"] = autosave

col1, col2 = st.sidebar.columns([1, 1])
with col1:
    if st.sidebar.button("💾 Guardar ahora", use_container_width=True):
        if immediate_autosave(reason="manual desde botón"):
            st.sidebar.success("✅ Guardado en GitHub")
        else:
            st.sidebar.error("❌ No se pudo guardar en GitHub")

with col2:
    if st.sidebar.button("🔄 Recargar", use_container_width=True, help="Recarga los datos desde GitHub"):
        st.experimental_rerun()

if "last_save_ts" in st.session_state:
    last_save = time.time() - st.session_state["last_save_ts"]
    if last_save < 60:
        st.sidebar.caption(f"✅ Guardado hace {int(last_save)}s")
    elif last_save < 3600:
        st.sidebar.caption(f"✅ Guardado hace {int(last_save/60)}m")
    else:
        st.sidebar.caption(f"✅ Guardado hace {int(last_save/3600)}h")

if st.session_state.get("autosave_enabled", True):
    st.sidebar.caption("🟢 Autosave habilitado")
else:
    st.sidebar.caption("🔴 Autosave deshabilitado")


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

if "last_saved_signature" not in st.session_state:
    st.session_state["last_saved_signature"] = current_state_signature()


# ============================================================
# TABS
# ============================================================

tabs = st.tabs(["📚 Datos", "🧰 Taller", "🧽 Lavado", "📦 Disponibilidad", "🚨 Alertas"])


# ================= DATOS =================
with tabs[0]:
    st.header("Datos")
    st.subheader("Proyectos")

    hide_100 = st.checkbox(
        "Ocultar proyectos al 100%",
        value=False,
        key="hide_100_proy"
    )

    # ✅ 1) DEFINIR proy_cfg PRIMERO
    proy_cfg = {
        "Proyecto": st.column_config.TextColumn("Proyecto", width="medium"),
        "Constructora": st.column_config.TextColumn("Const.", width="small"),
        "Tipo": st.column_config.SelectboxColumn(
            "Tipo",
            options=["Venta", "Arriendo", "Arriendo MO", "Reparación"],
            required=True,
            width="small",
        ),
        "Fecha_requerida": st.column_config.DateColumn(
            "F. Req", format="DD-MMM-YYYY", width="small"
        ),
        "Inicio_obra": st.column_config.DateColumn(
            "Inicio_obra", format="DD-MMM-YYYY", width="small"
        ),
        "Duracion_obra_meses": st.column_config.NumberColumn(
            "Duración", width="small"
        ),
        "Termino_obra": st.column_config.DateColumn(
            "Término_obra", format="DD-MMM-YYYY", disabled=True, width="small"
        ),
        "M2": st.column_config.NumberColumn("M2", width="small"),
        "Avance_pct": st.column_config.NumberColumn(
            "Av %", min_value=0, max_value=100, step=1, width="small"
        ),
        "Avance_m2": st.column_config.NumberColumn(
            "Av m²", disabled=True, width="small"
        ),
        "Ritmo_esperado": st.column_config.NumberColumn("Ritmo", width="small"),
        "WF600x2250_usado": st.column_config.NumberColumn("WF U", width="small"),
        "WF600x2250_nuevo": st.column_config.NumberColumn("WF N", width="small"),
        "CE600x1200_usado": st.column_config.NumberColumn("CE U", width="small"),
        "CE600x1200_nuevo": st.column_config.NumberColumn("CE N", width="small"),
        "Comentario": st.column_config.TextColumn("Comentario", width="medium"),
    }

    # ✅ 2) LUEGO preparar base y vista
    df_proy_base = st.session_state["df_proy"].copy()
    view_proy = df_proy_base.copy()

    av = pd.to_numeric(view_proy.get("Avance_pct"), errors="coerce").fillna(0)
    if hide_100:
        view_proy = view_proy[av < 100]

    # ✅ 3) RECIÉN AQUÍ usar proy_cfg
    df_proy = stable_data_editor(
        df_key="df_proy",
        widget_key="editor_proyectos_v2_fix",
        column_config=proy_cfg,
        schema_fn=schema_proyectos_keep_rowid,
        view_df=view_proy,
        height=_df_height(view_proy),
        num_rows="dynamic",
    )
    # ---------------- STOCK ----------------
    st.subheader("Stock")
    stock_cfg = {
        "Fecha": st.column_config.DateColumn("Fecha", format="DD-MMM-YYYY")
    }

    df_stock = stable_data_editor(
        df_key="df_stock",
        widget_key="editor_stock_v2_fix",
        column_config=stock_cfg,
        schema_fn=schema_stock_keep_rowid,
        view_df=st.session_state["df_stock"],
        height=_df_height(st.session_state["df_stock"]),
        num_rows="dynamic",
    )

    # ---------------- LAVADO ----------------
    st.subheader("Lavado")
    lav_cfg = {
        "Fecha Requerida": st.column_config.DateColumn(
            "Fecha requerida", format="DD-MMM-YYYY"
        ),
        "Inicio": st.column_config.DateColumn(
            "Inicio", format="DD-MMM-YYYY"
        ),
        "Termino": st.column_config.DateColumn(
            "Término", format="DD-MMM-YYYY"
        ),
        "Inicio_prog": st.column_config.DateColumn(
            "Inicio programado", format="DD-MMM-YYYY"
        ),
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

    # ---------------- ESTADO DE AUTOSAVE ----------------
    if autosave:
        st.info("Los cambios se guardan automáticamente en GitHub.")
    else:
        st.warning("Autosave deshabilitado. Usa el botón Guardar ahora para sincronizar.")

# ================= TALLER =================
with tabs[1]:
    st.header("Taller")
    df_proy_now = drop_internal_cols(st.session_state["df_proy"]).copy()

    base = df_proy_now.copy()
    base["Avance"] = base["Avance_pct"]
    base["Ritmo"] = base["Ritmo_esperado"]
    base["Fecha Requerida"] = base["Fecha_requerida"]

    res = programa_linea(base, ritmo_taller, HOY)
    
    taller_res_cfg = {
    "Fecha Requerida": st.column_config.DateColumn("Fecha Requerida", format="DD-MMM-YYYY"),
    "Inicio prog": st.column_config.DateColumn("Inicio prog", format="DD-MMM-YYYY"),
    "Fin prog": st.column_config.DateColumn("Fin prog", format="DD-MMM-YYYY"),}

    st.dataframe(res, height=_df_height(res), column_config=taller_res_cfg)

    export_block(res, name="Taller calculado", key_prefix="taller_calculado")


# ================= LAVADO =================
with tabs[2]:
    st.header("Lavado")
    df_lav_now = st.session_state["df_lav"].copy()
    res_lav = programa_linea(df_lav_now, ritmo_lavado, HOY)

    st.dataframe(res_lav, height=_df_height(res_lav))

    export_block(
        res_lav,
        name="Lavado calculado",
        key_prefix="lavado_calculado"
    )

# ================= DISPONIBILIDAD =================
with tabs[3]:
    df_stock_now = st.session_state["df_stock"].copy()
    df_proy_now = st.session_state["df_proy"].copy()
    disponibilidad_tab(df_stock_now, df_proy_now)


# ================= ALERTAS =================
with tabs[4]:
    alertas_tab(st.session_state["df_proy"], st.session_state["df_stock"])


if autosave:
    autosave_if_needed()



