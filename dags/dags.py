from datetime import datetime, timedelta

from airflow import DAG
from conveyor.operators import ConveyorContainerOperatorV2

aws_role = "mimir-iam-monthly-meteo-composite-{{ macros.conveyor.env() }}-vito"

default_args = {
    "owner": "Conveyor",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email": ["vincent.verelst@vito.be"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=60),
    "aws_role": aws_role,
}

dag = DAG(
    "monthly-meteo-composite",
    default_args=default_args,
    schedule="0 0 20 * *", # Run monthly on the 20th at 00:00 UTC, to ensure all data for the previous month is available
    max_active_runs=1,
    catchup=False,
)


def create_container_job(
    job: str,
    task_id: str | None = None,
    instance_type: str = "cx.xlarge",
    instance_life_cycle: str = "spot",
    trigger_rule: str = "all_success",
    collection_id: str | None = None,
) -> ConveyorContainerOperatorV2:
    arguments = ["-m", f"{job}.main"]

    if collection_id:
        arguments.extend(["--collection-id", collection_id])

    return ConveyorContainerOperatorV2(
        dag=dag,
        task_id=task_id or job,   # this needs to be unique per task, so we use the job name as default, but allow overriding it if needed (e.g. for the postprocess task which needs the collection_id as argument and thus cannot use the same task_id)
        cmds=["python"],
        arguments=arguments,
        trigger_rule=trigger_rule,
        instance_type=instance_type,
        instance_life_cycle=instance_life_cycle,
    )


with dag:
    monthly_composite_task = create_container_job("monthly_meteo_composite")
    monthly_postprocess_task = create_container_job("postprocess", task_id="monthly_postprocess", collection_id="agera5_monthly_composite")
    monthly_composite_task >> monthly_postprocess_task  # First run monthly_composite_task, upon successful completion run monthly_postprocess_task

    dekadal_composite_task = create_container_job("dekadal_meteo_composite")
    dekadal_postprocess_task = create_container_job("postprocess", task_id="dekadal_postprocess", collection_id="agera5_dekadal_composite")
    dekadal_composite_task >> dekadal_postprocess_task  # First run dekadal_composite_task, upon successful completion run dekadal_postprocess_task
