from unittest.mock import Mock

from studio.l4_frameworks_and_drivers.studio import Studio


def test_start_connect_without_a_transport_returns_no_phone_connection():
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=Mock()
    )
    assert studio.start_connect() is None
