-- migration_presupuesto_lineas_uid_v1.sql
--
-- Discriminador de línea para la captura manual de Presupuesto de Ventas/Compras.
-- Permite varias líneas para el mismo (company, cliente_excel, codigo_origen,
-- producto_excel): las filas de Excel/staging quedan con linea_uid = '' (una línea
-- por identidad, comportamiento previo); las líneas capturadas a mano reciben un
-- uuid propio. El índice único se reconstruye incluyendo linea_uid al final.

ALTER TABLE presupuesto_ventas
  ADD COLUMN linea_uid VARCHAR(32) NOT NULL DEFAULT '' AFTER producto_excel;
ALTER TABLE presupuesto_ventas
  DROP INDEX uk_presupuesto_ventas_excel,
  ADD UNIQUE KEY uk_presupuesto_ventas_excel
    (id_carga, seccion, region, anio, mes, company, cliente_excel,
     codigo_origen, producto_excel(100), linea_uid);

ALTER TABLE presupuesto_ventas_lineas
  ADD COLUMN linea_uid VARCHAR(32) NOT NULL DEFAULT '' AFTER producto_excel;
ALTER TABLE presupuesto_ventas_lineas
  DROP INDEX uk_pv_lineas,
  ADD UNIQUE KEY uk_pv_lineas
    (id_carga, company, cliente_excel(100), codigo_origen,
     producto_excel(100), linea_uid);

ALTER TABLE presupuesto_compras
  ADD COLUMN linea_uid VARCHAR(32) NOT NULL DEFAULT '' AFTER producto_excel;
ALTER TABLE presupuesto_compras
  DROP INDEX uk_presupuesto_compras_excel,
  ADD UNIQUE KEY uk_presupuesto_compras_excel
    (id_carga, seccion, region, anio, mes, company, cliente_excel,
     codigo_origen, producto_excel(100), linea_uid);

ALTER TABLE presupuesto_compras_lineas
  ADD COLUMN linea_uid VARCHAR(32) NOT NULL DEFAULT '' AFTER producto_excel;
ALTER TABLE presupuesto_compras_lineas
  DROP INDEX uk_pc_lineas,
  ADD UNIQUE KEY uk_pc_lineas
    (id_carga, company, cliente_excel(100), codigo_origen,
     producto_excel(100), linea_uid);
