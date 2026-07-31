import unittest
from unittest.mock import patch

from mcp_server_openviking_controlplane.client import ControlPlaneClient
from mcp_server_openviking_controlplane.config import ControlPlaneConfig


class CollectionUpdateContractTest(unittest.TestCase):
    def setUp(self):
        self.client = ControlPlaneClient(ControlPlaneConfig(api_key="ark-test"))

    def test_description_update_preserves_model_configuration(self):
        with patch.object(
            self.client,
            "_request",
            return_value={"Success": True},
        ) as request:
            self.client.update_collection(
                "ov-example",
                description="new description",
            )

        request.assert_called_once_with(
            "UpdateOpenVikingCollection",
            {
                "ResourceID": "ov-example",
                "Description": "new description",
            },
        )

    def test_billing_update_preserves_model_configuration(self):
        with patch.object(
            self.client,
            "_request",
            return_value={"Success": True},
        ) as request:
            self.client.update_collection(
                "ov-example",
                pay_type="volc_pay",
            )

        request.assert_called_once_with(
            "UpdateOpenVikingCollection",
            {
                "ResourceID": "ov-example",
                "PaymentConfig": {"PayType": "volc_pay"},
            },
        )

    def test_explicit_model_updates_are_forwarded(self):
        with patch.object(
            self.client,
            "_request",
            return_value={"Success": True},
        ) as request:
            self.client.update_collection(
                "ov-example",
                vlm={
                    "ModelName": "doubao-seed-2.0-lite",
                    "Credentials": [
                        {
                            "Source": "agentplan",
                            "ApiKey": "ark-model",
                        }
                    ],
                },
            )

        request.assert_called_once_with(
            "UpdateOpenVikingCollection",
            {
                "ResourceID": "ov-example",
                "VLM": {
                    "ModelName": "doubao-seed-2.0-lite",
                    "Credentials": [
                        {
                            "Source": "agentplan",
                            "ApiKey": "ark-model",
                        }
                    ],
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
