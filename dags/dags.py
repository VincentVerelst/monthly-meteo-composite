from datetime import datetime, timedelta

from airflow import DAG
from conveyor.operators import ConveyorContainerOperatorV2

aws_role = "mimir-iam-monthly-meteo-composite-{{ macros.conveyor.env() }}-vito"

default_args = {
    "owner": "Conveyor",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email": [],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
    "aws_role": aws_role,
}

dag = DAG(
    "monthly-meteo-composite",
    default_args=default_args,
    schedule_interval=None,
    max_active_runs=1,
)


def create_container_job(
    job: str,
    instance_type: str = "cx.xlarge",
    instance_life_cycle: str = "spot",
    trigger_rule: str = "all_success",
) -> ConveyorContainerOperatorV2:
    """
    Create a ConveyorContainerOperatorV2 for the given job.
    Args:
        job: The name of the job to run. Should be the name of the Python module containing the job's main function.
        instance_type (str): The type of cloud instance to use. (e.g. cx.micro (1CPU), cx.large (2CPU), cx.xlarge (4CPU))
        instance_life_cycle (str): The lifecycle of the cloud instance (spot or on-demand).
        trigger_rule: The Airflow trigger rule for the task.

    Returns:
        A ConveyorContainerOperatorV2 for the given job.
    """

    arguments = ["-m", f"{job}.main", "--env", "{{ macros.conveyor.env() }}"]

    return ConveyorContainerOperatorV2(
        dag=dag,
        task_id=job,
        cmds=["python"],
        arguments=arguments,
        trigger_rule=trigger_rule,
        instance_type=instance_type,
        instance_life_cycle=instance_life_cycle,
    )


with dag:
    create_container_job("test_job")
