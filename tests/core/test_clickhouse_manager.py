import unittest
from unittest.mock import MagicMock, patch
import threading
from core.clickhouse_manager import ClickHouseManager, get_manager

class TestClickHouseManager(unittest.TestCase):

    def setUp(self):
        # Réinitialise le singleton avant chaque test pour éviter les effets de bord
        ClickHouseManager._instance = None

    @patch('core.clickhouse_manager.clickhouse_connect.get_client')
    def test_singleton_behavior(self, mock_get_client):
        """Vérifie que la classe implémente correctement un Singleton."""
        manager1 = ClickHouseManager.get_instance()
        manager2 = get_manager()  # Utilise le raccourci global
        
        self.assertIs(manager1, manager2)

    @patch('core.clickhouse_manager.clickhouse_connect.get_client')
    def test_connect_creates_client_once_per_thread(self, mock_get_client):
        """Vérifie que le client se connecte avec les bons paramètres et réutilise le client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        manager = ClickHouseManager.get_instance()
        
        # Premier appel à connect()
        client1 = manager.connect()
        # Deuxième appel à connect()
        client2 = manager.connect()

        # Le driver clickhouse_connect ne doit être appelé qu'une seule fois grâce au threading.local
        mock_get_client.assert_called_once_with(
            host=manager.host,
            port=manager.port,
            username=manager.user,
            password=manager.password
        )
        self.assertIs(client1, mock_client)
        self.assertIs(client2, mock_client)

    @patch('core.clickhouse_manager.clickhouse_connect.get_client')
    def test_query_passes_parameters(self, mock_get_client):
        """Vérifie que la méthode query transmet correctement le SQL et les paramètres."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        manager = ClickHouseManager.get_instance()
        sql = "SELECT * FROM my_table WHERE id = %(id)s"
        params = {"id": 42}
        
        manager.query(sql, parameters=params)
        
        # Vérifie que la requête a été déléguée au client interne
        mock_client.query.assert_called_once_with(sql, parameters=params)

    @patch('core.clickhouse_manager.clickhouse_connect.get_client')
    def test_close_all(self, mock_get_client):
        """Vérifie que close_all ferme bien tous les clients ouverts et nettoie le thread local."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        manager = ClickHouseManager.get_instance()
        manager.connect()  # Ouvre une connexion
        
        manager.close_all()
        
        # Le client doit être fermé
        mock_client.close.assert_called_once()
        # L'attribut local du thread doit être nettoyé
        self.assertFalse(hasattr(manager._local, "client"))

if __name__ == '__main__':
    unittest.main()