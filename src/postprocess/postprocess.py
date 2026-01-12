import mimir_utils
import openeo
import pystac
import pystac_client
import requests
from openeo.rest.auth.oidc import (
    OidcClientInfo,
    OidcProviderInfo,
    OidcResourceOwnerPasswordAuthenticator,
)
from requests.auth import AuthBase
import logging
from datetime import date
from dateutil.relativedelta import relativedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


NEW_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[180, -90], [180, 90], [-180, 90], [-180, -90], [180, -90]]],
}

NEW_BBOX = [-180.0, -90.0, 180.0, 90.0]

COLLECTION_ID = "agera5_monthly_composite"

ITEM_ASSETS = {
    "temperature-mean": {
        "type": "image/tiff; application=geotiff",
        "title": "temperature-mean",
        "description": "temperature-mean",
        "roles": ["data"],
        "eo:bands": [{"name": "temperature-mean", "description": "temperature-mean"}],
    },
    "precipitation-flux": {
        "type": "image/tiff; application=geotiff",
        "title": "precipitation-flux",
        "description": "precipitation-flux",
        "roles": ["data"],
        "eo:bands": [
            {"name": "precipitation-flux", "description": "precipitation-flux"}
        ],
    },
}

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
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    ]

    item.properties["proj:geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [
                [180.05, -90.05],
                [180.05, 90.05],
                [-180.05, 90.05],
                [-180.05, -90.05],
                [180.05, -90.05],
            ]
        ],
    }
    item.properties["proj:bbox"] = [-180.05, -90.05, 180.05, 90.05]
    item.properties["proj:code"] = "EPSG:4326"
    item.properties["proj:shape"] = [1801, 3601]
    item.properties["proj:transform"] = [0.1, 0, -180.05, 0, -0.1, 90.05]

    for key in list(item.assets.keys()):
        asset = item.assets.pop(key)
        asset.href = asset.href.replace("s3://", "https://s3.waw3-1.cloudferro.com/")

        asset.extra_fields["geometry"] = NEW_GEOMETRY
        asset.extra_fields["raster:bands"] = [{"nodata": 65535, "data_type": "uint16"}]
        asset.extra_fields['bbox'] = NEW_BBOX
        asset.extra_fields['geometry'] = NEW_GEOMETRY

        if "bands" in asset.extra_fields:
            asset.extra_fields["eo:bands"] = asset.extra_fields.pop("bands")
        if "precipitation" in key:
            item.assets["precipitation-flux"] = asset
        elif "temperature" in key:
            item.assets["temperature-mean"] = asset
        else:
            raise ValueError(f"Unknown asset key: {key}")

    item_dict = item.to_dict()
    item_dict["stac_version"] = "1.1.0"
    return item_dict

def process_collection(collection: pystac.Collection) -> dict:
    collection.stac_extensions = [
        "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    ]

    collection.links = []

    collection_dict = collection.to_dict()
    collection_dict["stac_version"] = "1.1.0"

    end_date = (date.today() - relativedelta(months=1)).replace(day=1).strftime("%Y-%m-%d")
    collection_dict["extent"]["temporal"]["interval"] = [["2015-01-01T00:00:00Z", f"{end_date}T23:59:59Z"]]

    collection_dict["item_assets"] = ITEM_ASSETS

    collection_dict['_auth'] = {
                "read": ["anonymous"],
                "write": ["stac-openeo-admin", "stac-openeo-editor"],
            }

    return collection_dict

def postprocess() -> None:

    logger.info("Starting postprocessing of STAC items.")
    parameters_api = mimir_utils.MimirClient.connect(
        data_product="monthly-meteo-composite", environment="experimentation"
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
        collections=[COLLECTION_ID],
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
        url=f"https://stac.openeo.vito.be/collections/{COLLECTION_ID}/bulk_items",
        json={
            "method": "upsert",
            "items": new_items,
        },
        auth=auth,
    )

    resp.raise_for_status()
    logger.info("Successfully uploaded processed items to STAC API.")

    logger.info("Fetching collection from STAC API.")
    collection = pystac.read_file(
        f"https://stac.openeo.vito.be/collections/{COLLECTION_ID}")
    logger.info("Processing collection.")
    new_collection = process_collection(collection)
    logger.info("Uploading processed collection to STAC API.")
    resp = _get_retry_session().put(
        url=f"https://stac.openeo.vito.be/collections/{COLLECTION_ID}",
        json=new_collection,
        auth=auth,
    )
    resp.raise_for_status()
    logger.info(f"Uploaded collection response: {resp.status_code} - {resp.text}")
    logger.info("Successfully uploaded processed collection to STAC API.")
