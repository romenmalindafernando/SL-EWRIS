"""Primary SL-EWRIS Streamlit entry point."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("cloud_demo.py")), run_name="__main__")
