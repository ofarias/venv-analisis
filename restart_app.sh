#!/bin/bash
fuser -k 8501/tcp 2>/dev/null
systemctl restart streamlit.service
echo "app reiniciada"
