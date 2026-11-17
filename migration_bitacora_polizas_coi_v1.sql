-- Bitácora de pólizas que la app crea en COI (ventas y costo de venta).
-- COI (POLIZASxx) no guarda quién capturó la póliza ni cuándo, así que se
-- registra aquí justo después del commit en COI. También se usa para decir
-- quién creó la póliza cuando alguien intenta contabilizar el mismo día otra vez.
-- Ver _registrar_bitacora_poliza en models/conta45_model.py.

CREATE TABLE IF NOT EXISTS iaspel.bitacora_polizas_coi (
  id INT NOT NULL AUTO_INCREMENT,
  origen VARCHAR(30) NOT NULL,            -- 'ventas' | 'costo_venta'
  tipo_poli VARCHAR(5) NOT NULL,
  num_poliz VARCHAR(10) NOT NULL,
  periodo INT NOT NULL,
  ejercicio INT NOT NULL,
  fecha_pol DATE NOT NULL,
  concepto VARCHAR(120) NOT NULL,
  num_docs INT NULL,
  num_partidas INT NULL,
  total_cargos DECIMAL(18,2) NULL,
  usuario VARCHAR(100) NULL,
  fecha_creacion DATETIME NOT NULL,      -- la app manda NOW(); este MySQL no acepta DEFAULT CURRENT_TIMESTAMP en DATETIME
  PRIMARY KEY (id),
  KEY idx_poliza (ejercicio, periodo, tipo_poli, num_poliz),
  KEY idx_fecha_pol (fecha_pol, origen)
);
