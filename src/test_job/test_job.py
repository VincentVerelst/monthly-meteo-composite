import openeo


def test_job() -> None:
    c = openeo.connect("openeo.vito.be").authenticate_oidc()

    bbox = {"north": 52.5, "south": 52.45, "east": 13.4, "west": 13.35, "crs": 4326}

    s2 = c.load_collection(
        collection_id="SENTINEL2_L2A",
        spatial_extent=bbox,
        temporal_extent=["2020-01-01", "2020-01-10"],
        bands=["B04"],
    )

    s2.execute_batch(
        out_format="GTiff",
        title="small test job for Conveyor",
    )
