app = FastAPI()

@app.get("/descargar_documento")
def descargar_documento(id: int):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nombre_archivo, archivo FROM versiones_documento WHERE documento_id = %s", (id,))
    doc = cursor.fetchone()
    conn.close()

    if doc:
        return StreamingResponse(
            BytesIO(doc["archivo"]),
            headers={"Content-Disposition": f"attachment; filename={doc['nombre_archivo']}"},
            media_type="application/octet-stream"
        )
    else:
        return {"error": "Archivo no encontrado"}