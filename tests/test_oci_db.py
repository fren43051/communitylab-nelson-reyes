"""
Pruebas unitarias para el conector de base de datos OCI (src/storage/oci_db.py).
Verifica que las credenciales se resuelvan desde el gestor de secretos y que las
operaciones SQL se invoquen correctamente (con dobles para ejecucion offline).
"""
import pytest
from unittest.mock import MagicMock, patch

from src.storage import oci_db


def test_obtener_conexion_db_usa_secretos(monkeypatch):
    valores_secretos = {
        "DB_USER": "ADMIN",
        "DB_PASSWORD": "PasswordSecreta123#",
        "DB_CONNECT_STRING": "tcps://adb.us-phoenix-1.oraclecloud.com:1522/test",
    }
    monkeypatch.setattr(oci_db, "requerir_secreto", lambda nombre, pista: valores_secretos[nombre])

    mock_connect = MagicMock()
    with patch("oracledb.connect", mock_connect):
        conn = oci_db.obtener_conexion_db()
        mock_connect.assert_called_once_with(
            user="ADMIN",
            password="PasswordSecreta123#",
            dsn="tcps://adb.us-phoenix-1.oraclecloud.com:1522/test",
        )
        assert conn == mock_connect.return_value


def test_guardar_interacciones_lista_vacia():
    resultado = oci_db.guardar_interacciones([])
    assert resultado == 0


def test_guardar_paquete_distribucion_mock():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch.object(oci_db, "obtener_conexion_db", return_value=mock_conn):
        paquete_mock = {
            "resumen_comunidad": {
                "origen_comunidad": "linkedin",
                "total_interacciones_procesadas": 10,
                "registros_validos": 8,
                "registros_rechazados": 2,
                "sentimiento_predominante": "positivo",
            },
            "control_revision_humana": {
                "numero_revision": 1,
                "estado_decision": "aprobado",
                "revisor": "nelson.reyes",
                "fecha_decision": "2026-10-12",
                "comentarios": "Aprobado sin cambios",
            },
        }
        res = oci_db.guardar_paquete_distribucion(paquete_mock, periodo_referencia="2026-10-12")

        assert res["status"] == "guardado_en_db"
        assert res["id_paquete"] == "2026-10-12-1"
        assert mock_cursor.execute.called
        assert mock_conn.commit.called
