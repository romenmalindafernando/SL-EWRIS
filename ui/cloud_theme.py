
"""Read-only SL-EWRIS public demo visual styling."""

import streamlit as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply_cloud_theme():

    st.markdown("""
    <style>

    :root {
        --ewris-navy: #173B53;
        --ewris-teal: #0D9488;
        --ewris-cyan: #118DA2;
        --ewris-border: #DCE9EE;
    }

    [data-testid="stAppViewContainer"] {
        background:
            linear-gradient(
                145deg,
                #F8FBFD 0%,
                #F0F8FA 55%,
                #F8FCFD 100%
            );
    }

    [data-testid="stSidebar"] {
        background:
            linear-gradient(
                160deg,
                #FFFFFF 0%,
                #F3FAFB 100%
            ) !important;

        border-right:
            1px solid #DCE9EE;
    }

    [data-testid="stSidebarNav"] {
        display: none !important;
    }

    [data-testid="stSidebar"] button {
        border-radius: 13px !important;
        transition:
            background-color .25s ease,
            box-shadow .25s ease,
            transform .25s ease;
    }

    [data-testid="stSidebar"] button:hover {
        background: #E2F5F1 !important;
        transform: translateX(3px);
        box-shadow:
            0 5px 15px rgba(13,148,136,.09);
    }

    h1, h2, h3 {
        color: #173B53 !important;
        letter-spacing: -.4px;
    }

    /* KPI cards */
    [data-testid="stMetric"] {
        min-height: 138px;
        height: auto !important;
        min-width: 0 !important;

        padding: 19px !important;
        border-radius: 18px !important;

        border: 1px solid #C3E3DF !important;

        background:
            linear-gradient(
                135deg,
                rgba(255,255,255,.95),
                #E7F7F3
            ) !important;

        box-shadow:
            0 6px 20px rgba(30,80,100,.06);

        overflow: visible !important;

        transition:
            transform .25s ease,
            box-shadow .25s ease;
    }

    [data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow:
            0 10px 24px rgba(25,90,110,.11);
    }

    [data-testid="stColumn"]:nth-child(4n+2)
    [data-testid="stMetric"] {
        background:
            linear-gradient(135deg,#FFFFFF,#E9F3FC)
            !important;
        border-color: #C8DDF0 !important;
    }

    [data-testid="stColumn"]:nth-child(4n+3)
    [data-testid="stMetric"] {
        background:
            linear-gradient(135deg,#FFFFFF,#E7F7FA)
            !important;
        border-color: #BFE4EC !important;
    }

    [data-testid="stColumn"]:nth-child(4n)
    [data-testid="stMetric"] {
        background:
            linear-gradient(135deg,#FFFFFF,#F0EFFB)
            !important;
        border-color: #DCD8F0 !important;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        overflow: visible !important;
        max-height: none !important;
        height: auto !important;
        white-space: normal !important;
        min-width: 0 !important;
    }

    [data-testid="stMetricLabel"] *,
    [data-testid="stMetricValue"] * {
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        text-overflow: clip !important;
        -webkit-line-clamp: unset !important;
    }

    [data-testid="stMetricLabel"] * {
        color: #24747B !important;
        font-size: 14px !important;
        font-weight: 650 !important;
        line-height: 1.45 !important;
    }

    [data-testid="stMetricValue"] * {
        color: #19394F !important;
        font-size: clamp(20px,2vw,30px) !important;
        font-weight: 750 !important;
        line-height: 1.3 !important;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        font-weight: 600;
    }
    /* Page entry */
    @keyframes ewrisCloudEnter {
        from {
            opacity: 0;
            transform: translateY(9px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    [data-testid="stMain"] .block-container {
        animation:
            ewrisCloudEnter .4s
            cubic-bezier(.22,1,.36,1) both;
    }

    @media (prefers-reduced-motion: reduce) {
        [data-testid="stMain"] .block-container {
            animation: none !important;
        }

        [data-testid="stSidebar"] button,
        [data-testid="stMetric"] {
            transition: none !important;
            transform: none !important;
        }
    }

    </style>
    """, unsafe_allow_html=True)


def show_cloud_brand():
    """Insert the logo before existing sidebar controls."""

    image = ROOT / "assets" / "sl_ewris_logo.png"

    if image.exists():
        with st.sidebar:
            st.image(str(image), width="stretch")
