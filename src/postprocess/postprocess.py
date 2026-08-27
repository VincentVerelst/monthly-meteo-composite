import logging

import mimir_utils
import pystac
import pystac_client
import requests
from openeo.rest.auth.oidc import (
    OidcClientInfo,
    OidcProviderInfo,
    OidcResourceOwnerPasswordAuthenticator,
)
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


NEW_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[180, -90], [180, 90], [-180, 90], [-180, -90], [180, -90]]],
}

NEW_BBOX = [-180.0, -90.0, 180.0, 90.0]

_retry_session = None


def _get_retry_session() -> requests.Session:
    """Get or create a requests session with retry logic."""
    global _retry_session
    if _retry_session is not None:
        return _retry_session

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "PUT", "POST"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    _retry_session = session
    return _retry_session


class VitoStacApiAuthentication(AuthBase):
    """Class that handles authentication for the VITO STAC API. https://stac.openeo.vito.be/"""

    def __init__(self, **kwargs):
        self.username = kwargs.get("username")
        self.password = kwargs.get("password")

    def __call__(self, request):
        request.headers["Authorization"] = self.get_access_token()
        return request

    def get_access_token(self) -> str:
        """Get API bearer access token via password flow.

        Returns
        -------
        str
            A string containing the bearer access token.
        """
        provider_info = OidcProviderInfo(
            issuer="https://sso.terrascope.be/auth/realms/terrascope"
        )

        client_info = OidcClientInfo(
            client_id="terracatalogueclient",
            provider=provider_info,
        )

        if self.username and self.password:
            authenticator = OidcResourceOwnerPasswordAuthenticator(
                client_info=client_info, username=self.username, password=self.password
            )
        else:
            raise ValueError(
                "Credentials are required to obtain an access token. Please set STAC_API_USERNAME and STAC_API_PASSWORD environment variables."
            )

        tokens = authenticator.get_tokens()

        return f"Bearer {tokens.access_token}"


def process_item(item: pystac.Item) -> dict:
    item.geometry = NEW_GEOMETRY
    item.bbox = NEW_BBOX
    item.stac_extensions = [
        "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
    ]

    for key in list(item.assets.keys()):
        asset = item.assets.pop(key)
        asset.href = asset.href.replace("s3://", "https://s3.waw3-1.cloudferro.com/")

        if "precipitation" in key:
            item.assets["precipitation-flux"] = asset
        elif "temperature" in key:
            item.assets["temperature-mean"] = asset
        else:
            raise ValueError(f"Unknown asset key: {key}")

    item_dict = item.to_dict()
    item_dict["stac_version"] = "1.1.0"
    return item_dict


def postprocess(collection_id: str) -> None:
    logger.info("Starting postprocessing of STAC items.")
    parameters_api = mimir_utils.MimirClient.connect(
        data_product="monthly-meteo-composite", environment="publishing"
    )
    product_parameters_api = parameters_api.aws.parameters.data_product

    logger.info("Retrieving STAC API credentials from Mimir.")
    stac_api_username = product_parameters_api.get("stac_api_username")
    stac_api_password = product_parameters_api.get("stac_api_password")
    logger.info("Retrieved STAC API credentials from Mimir.")

    auth = VitoStacApiAuthentication(
        username=stac_api_username, password=stac_api_password
    )

    client = pystac_client.Client.open("https://stac.openeo.vito.be/")

    search = client.search(
        collections=[collection_id],
        method="POST",
    )

    logger.info("Fetching items from STAC API.")
    items = list(search.items())
    logger.info(f"Fetched {len(items)} items from STAC API.")

    new_items = {}
    logger.info(f"Processing {len(items)} items.")
    for item in items:
        new_items[item.id] = process_item(item)

    logger.info("Successfully processed all items. Uploading to STAC API.")
    resp = _get_retry_session().post(
        url=f"https://stac.openeo.vito.be/collections/{collection_id}/bulk_items",
        json={
            "method": "upsert",
            "items": new_items,
        },
        auth=auth,
    )

    resp.raise_for_status()
    logger.info("Successfully uploaded processed items to STAC API.")
