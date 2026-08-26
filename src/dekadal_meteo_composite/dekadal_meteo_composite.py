import logging
from datetime import date

import mimir_utils
import openeo
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def dekadal_meteo_composite() -> None:
    parameters_api = mimir_utils.MimirClient.connect(
        data_product="monthly-meteo-composite", environment="publishing"
    )
    product_parameters_api = parameters_api.aws.parameters.data_product

    client_id = product_parameters_api.get("openeo_client_id")
    client_secret = product_parameters_api.get("openeo_client_secret")

    logger.info("Authenticating to OpenEO Terrascope backend...")
    c = openeo.connect("openeo.terrascope.be").authenticate_oidc_client_credentials(
        client_id=client_id, client_secret=client_secret
    )
    logger.info("Authentication successful.")

    # Define end date as the first day of the previous month, to make sure we only have full month composites

    if not date.today().day >= 20:
        logger.info(
            "Current date is before the 20th of the month, adjusting end date to two months ago."
        )
        start_date = (
            (date.today() - relativedelta(months=2)).replace(day=1).strftime("%Y-%m-%d")
        )
        end_date = (
            (date.today() - relativedelta(months=1)).replace(day=1).strftime("%Y-%m-%d")
        )
    else:
        logger.info(
            "Current date is on or after the 20th of the month, using previous month as end date."
        )
        start_date = (
            (date.today() - relativedelta(months=1)).replace(day=1).strftime("%Y-%m-%d")
        )
        end_date = date.today().replace(day=1).strftime("%Y-%m-%d")

    logger.info("Loading AGERA5 collection with end date %s", end_date)
    meteo = c.load_collection(
        collection_id="AGERA5",
        spatial_extent={
            "west": -180.0,
            "south": -90.0,
            "east": 180.0,
            "north": 90.0,
            "crs": "EPSG:4326",
        },
        temporal_extent=[start_date, end_date],
        bands=["temperature-mean", "precipitation-flux"],
    )

    meteo_temp = meteo.filter_bands(bands=["temperature-mean"])
    meteo_temp = meteo_temp.aggregate_temporal_period(period="dekad", reducer="mean")
    meteo_prec = meteo.filter_bands(bands=["precipitation-flux"])
    meteo_prec = meteo_prec.aggregate_temporal_period(period="dekad", reducer="sum")

    meteo = meteo_temp.merge_cubes(meteo_prec)
    meteo = meteo.linear_scale_range(0, 65534, 0, 65534)

    save_result_options = {
        "separate_asset_per_band": True,
    }

    result_cube = meteo.save_result(
        format="GTiff",
        options=save_result_options,
    )

    result_cube = result_cube.export_workspace(
        workspace="worldcereal-stac-openeo-agera5-monthly-s3-workspace",
        merge="agera5_dekadal_composite",
    )

    job_options = {
        "executor_memory": "4G",
        "driver_memory": "4G",
        "executor_memoryOverhead": "4G",
        "omit-derived-from-links": True,
        "export-workspace-enable-merge": True,
        "stac-version": "1.1",
    }

    job = result_cube.create_job(
        job_options=job_options,
        title="AGERA5 Dekadal Composite Job",
    )

    job.start_and_wait()
