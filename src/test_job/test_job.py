import mimir_utils
import openeo


def test_job() -> None:
    parameters_api = mimir_utils.MimirClient.connect(
        data_product="monthly-meteo-composite", environment="experimentation"
    )
    product_parameters_api = parameters_api.aws.parameters.data_product

    client_id = product_parameters_api.get("openeo_client_id")
    client_secret = product_parameters_api.get("openeo_client_secret")

    c = openeo.connect("openeo.vito.be").authenticate_oidc_client_credentials(
        client_id=client_id, client_secret=client_secret, provider_id="terrascope"
    )

    bbox = {"north": 52.5, "south": 52.45, "east": 13.4, "west": 13.35, "crs": 4326}

    s2 = c.load_collection(
        collection_id="SENTINEL2_L2A",
        spatial_extent=bbox,
        temporal_extent=["2020-01-01", "2020-01-10"],
        bands=["B04"],
    )

    s2.execute_batch(
        out_format="GTiff",
        title="small test j for Conveyor",
    )
