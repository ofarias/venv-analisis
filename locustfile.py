from locust import HttpUser, task, between

class UsuarioSimulado(HttpUser):
    wait_time = between(1, 3)  # Tiempo entre solicitudes por usuario (segundos)

    @task
    def acceder_a_inicio(self):
        self.client.get("/")  # Ruta principal

    @task
    def acceder_a_ver_documentos(self):
        self.client.get("/?ver_docs")  # Ajusta según la ruta real

    @task
    def acceder_a_matriz_permisos(self):
        self.client.get("/?exp_permisos")  # Ajusta si tiene una ruta propia

    # Puedes agregar más tareas si tienes endpoints personalizados
    