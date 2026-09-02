import unittest

from PySide6.QtCore import QObject

from sdeck.obs import ObsConnection, ObsManager


class ObsConfirmationTests(unittest.TestCase):
    def make_connection(self) -> ObsConnection:
        connection = ObsConnection.__new__(ObsConnection)
        QObject.__init__(connection)
        connection.pending = {}
        connection.scenes = []
        connection.sources = {}
        connection.groups = {}
        connection.inputs = []
        return connection

    def test_rejected_request_does_not_change_local_state(self) -> None:
        connection = self.make_connection()
        changes = []
        connection.state_changed.connect(lambda *args: changes.append(args))
        connection.pending["request"] = {
            "request_type": "SetInputMute",
            "target": "Micrófono",
            "desired": True,
        }
        connection._response(
            {
                "requestId": "request",
                "requestStatus": {"result": False, "comment": "OBS no disponible"},
            }
        )
        self.assertEqual(changes, [])

    def test_confirmed_request_updates_local_state(self) -> None:
        connection = self.make_connection()
        changes = []
        connection.state_changed.connect(lambda *args: changes.append(args))
        connection.pending["request"] = {
            "request_type": "SetInputMute",
            "target": "Micrófono",
            "desired": True,
        }
        connection._response({"requestId": "request", "requestStatus": {"result": True}})
        self.assertEqual(changes, [("input_mute", "", "Micrófono", True)])

    def test_catalog_responses_publish_scenes_sources_and_inputs(self) -> None:
        connection = self.make_connection()
        catalogs = []
        queued = []
        connection.catalog_changed.connect(catalogs.append)
        connection.request = lambda request_type, data, context=None: queued.append((request_type, data, context))
        connection.pending["scenes"] = {"request_type": "GetSceneList"}
        connection._response(
            {
                "requestId": "scenes",
                "requestStatus": {"result": True},
                "responseData": {"scenes": [{"sceneName": "Principal"}, {"sceneName": "Cámara"}]},
            }
        )
        self.assertEqual(catalogs[-1]["scenes"], ["Principal", "Cámara"])
        self.assertEqual([item[0] for item in queued], ["GetSceneItemList", "GetSceneItemList"])
        connection.pending["sources"] = {"request_type": "GetSceneItemList", "scene": "Principal"}
        connection._response(
            {
                "requestId": "sources",
                "requestStatus": {"result": True},
                "responseData": {"sceneItems": [{"sourceName": "Captura"}, {"sourceName": "Micrófono"}]},
            }
        )
        connection.pending["inputs"] = {"request_type": "GetInputList"}
        connection._response(
            {
                "requestId": "inputs",
                "requestStatus": {"result": True},
                "responseData": {"inputs": [{"inputName": "Micrófono"}]},
            }
        )
        self.assertEqual(catalogs[-1]["sources"]["Principal"], ["Captura", "Micrófono"])
        self.assertEqual(catalogs[-1]["inputs"], ["Micrófono"])

    def test_stream_state_requires_confirmation(self) -> None:
        connection = self.make_connection()
        changes = []
        connection.state_changed.connect(lambda *args: changes.append(args))
        connection.pending["start"] = {"request_type": "StartStream"}
        connection._response({"requestId": "start", "requestStatus": {"result": True}})
        self.assertEqual(changes, [("stream", "", "", True)])

    def test_source_toggle_reads_real_state_before_inverting_it(self) -> None:
        connection = self.make_connection()
        queued = []
        connection.request = lambda request_type, data, context=None: queued.append((request_type, data, context))
        connection.pending["enabled"] = {
            "request_type": "GetSceneItemEnabled",
            "operation": "source",
            "scene": "Chill",
            "container": "Chill",
            "target": "Logo neo",
            "toggle": True,
            "scene_item_id": 6,
        }
        connection._response({
            "requestId": "enabled",
            "requestStatus": {"result": True},
            "responseData": {"sceneItemEnabled": True},
        })
        self.assertEqual(queued[0][0], "SetSceneItemEnabled")
        self.assertFalse(queued[0][1]["sceneItemEnabled"])

    def test_exact_source_action_sets_requested_state(self) -> None:
        manager = ObsManager()
        queued = []

        class Connection:
            def request(self, request_type, data, context=None):
                queued.append((request_type, data, context))

        manager.connection = lambda *_args: Connection()
        manager.trigger("source", "Chill", "Camborder", False, "Can", exact=True)
        self.assertEqual(queued[0][0], "GetSceneItemId")
        self.assertEqual(queued[0][1], {"sceneName": "Can", "sourceName": "Camborder"})
        self.assertFalse(queued[0][2]["desired"])
        self.assertNotIn("toggle", queued[0][2])

    def test_group_catalog_publishes_children(self) -> None:
        connection = self.make_connection()
        catalogs = []
        connection.catalog_changed.connect(catalogs.append)
        connection.pending["group"] = {
            "request_type": "GetGroupSceneItemList",
            "scene": "Chill",
            "group": "Can",
        }
        connection._response({
            "requestId": "group",
            "requestStatus": {"result": True},
            "responseData": {"sceneItems": [{"sourceName": "Camborder"}]},
        })
        self.assertEqual(catalogs[-1]["groups"]["Chill"]["Can"], ["Camborder"])


if __name__ == "__main__":
    unittest.main()
