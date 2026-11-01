"""Read-only public demo sidebar, matching SL-EWRIS brand palette."""
from pathlib import Path
import base64
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MENU = [
    ("Overview", "overview.png", "overview"),
    ("Monthly Data", "monthly.png", "monthly"),
    ("Economic Trends", "trends.png", "trends"),
    ("Risk Analysis", "risk.png", "risk"),
    ("Data Quality", "quality.png", "quality"),
]


def image_data_uri(filename):
    f = ASSETS / filename
    if not f.is_file():
        return None
    mimetype = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(f.suffix.lower())
    if not mimetype:
        return None
    return "data:" + mimetype + ";base64," + base64.b64encode(f.read_bytes()).decode("ascii")


def render_cloud_sidebar():
    if st.session_state.get("cloud_tab") not in [x[0] for x in MENU]:
        st.session_state.cloud_tab = "Overview"

    css = ["""<style>
    [data-testid="stSidebar"] {background:linear-gradient(160deg,#ffffff,#f0f9fa)!important;border-right:1px solid #dce9ee}
    [data-testid="stSidebar"] .stButton button {
      display:flex!important;align-items:center!important;justify-content:flex-start!important;
      width:100%;min-height:56px;padding:9px 12px!important;gap:0;
      text-align:left!important;color:#23445d;border-radius:14px!important;
      background:rgba(255,255,255,.7);border:1px solid #e1ecf0;
      font-weight:650;transition:transform .23s ease,background-color .23s ease,box-shadow .23s ease;
    }
    [data-testid="stSidebar"] .stButton button:hover {
      background:#e3f6f2!important;border-color:#a9dbd2!important;
      color:#087c75!important;transform:translateX(3px);
      box-shadow:0 5px 18px rgba(13,148,136,.12);
    }
    [data-testid="stSidebar"] .stButton button[kind="primary"] {
      background:linear-gradient(110deg,#d8f2ec,#e8f8f7)!important;
      color:#087a72!important;border-color:#a8dbd3!important;
      box-shadow:0 5px 16px rgba(13,148,136,.09);
    }
    [data-testid="stSidebar"] .stButton button::before {
      content:"";display:inline-block;flex:none;width:37px;height:37px;margin-right:12px;
      background-size:contain;background-position:center;background-repeat:no-repeat;
      transition:transform .23s ease;
    }
    [data-testid="stSidebar"] .stButton button:hover::before {transform:scale(1.06)}
    [data-testid="stSidebar"] [data-testid="stImage"] img {object-fit:contain}
    .ewris-cloud-subtitle {text-align:center;color:#6b8192;font-size:11px;font-weight:600;letter-spacing:.15px}
    [data-testid="stMetric"] {min-width:0!important;min-height:140px;height:auto!important;overflow:visible!important;}
    [data-testid="stMetricLabel"] *,[data-testid="stMetricValue"] * {
      white-space:normal!important;overflow:visible!important;overflow-wrap:anywhere!important;
      text-overflow:clip!important;max-height:none!important;
    }
    @media (prefers-reduced-motion:reduce) {
      [data-testid="stSidebar"] .stButton button,[data-testid="stSidebar"] .stButton button::before{transition:none!important;transform:none!important}
    }
    """]
    for name, filename, slug in MENU:
        uri = image_data_uri(filename)
        if uri:
            css.append('.st-key-cloud_nav_' + slug + ' button::before{background-image:url("' + uri + '")!important;}')
        else:
            css.append('.st-key-cloud_nav_' + slug + ' button::before{background-color:#e0f3ef;border-radius:9px;}')
    css.append('</style>')
    st.markdown('\n'.join(css), unsafe_allow_html=True)

    with st.sidebar:
        logo = ASSETS / "brand.png"
        if logo.is_file():
            st.image(str(logo), width="stretch")
        else:
            st.markdown('## SL-EWRIS')
        st.markdown('<p class="ewris-cloud-subtitle">Economic Intelligence Platform</p>', unsafe_allow_html=True)
        st.divider()
        for name, _filename, slug in MENU:
            if st.button(name, key="cloud_nav_" + slug,
                         type="primary" if st.session_state.cloud_tab == name else "secondary",
                         width="stretch"):
                st.session_state.cloud_tab = name
                st.rerun()
        st.divider()
        st.caption('SL-EWRIS research platform · Neon PostgreSQL')


def render_project_navigation():
    """Expose the full application pages without a second Streamlit menu."""

    pages = [
        ("Full: Historical Risk Intelligence", "pages/38_Historical_Risk_Intelligence.py"),
        ("Full: Monthly Economic Monitoring", "pages/39_Monthly_Economic_Monitoring.py"),
        ("Full: Saved Monthly Data", "pages/40_Saved_Monthly_Economic_Data.py"),
        ("Full: Data Verification", "pages/41_Data_Verification.py"),
        ("Full: Data Quality Dashboard", "pages/42_Data_Quality_Dashboard.py"),
        ("Full: Unified Economic Intelligence", "pages/43_Unified_Economic_Intelligence.py"),
        ("Full: Preliminary Risk Score", "pages/44_Preliminary_Risk_Score.py"),
        ("Full: Risk Threshold Sensitivity", "pages/45_Risk_Threshold_Sensitivity.py"),
        ("Full: Historical Lead-Time Evaluation", "pages/46_Historical_Lead_Time_Evaluation.py"),
        ("Full: Point-in-Time Validation", "pages/47_Point_In_Time_Validation.py"),
        ("Full: Historical Data Freshness", "pages/48_Historical_Data_Freshness.py"),
        ("Full: Historical Evidence Coverage", "pages/51_Historical_Evidence_Coverage.py"),
        ("Full: CBSL Source Progress", "pages/53_CBSL_Source_Progress_Tracker.py"),
    ]
    with st.sidebar:
        st.divider()
        st.markdown("**Full SL-EWRIS application**")
        for label, path in pages:
            st.page_link(path, label=label)
