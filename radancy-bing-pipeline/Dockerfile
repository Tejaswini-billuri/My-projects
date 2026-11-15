# Airflow 3 image with this project installed. Used by docker-compose.yml.
FROM apache/airflow:3.1.8-python3.12

USER root
COPY --chown=airflow:root . /opt/bing-pipeline
USER airflow

WORKDIR /opt/bing-pipeline
# The image already pins Airflow + SQLAlchemy; install only what the pipeline adds on top.
RUN pip install --no-cache-dir -e . --no-deps \
 && pip install --no-cache-dir "pandas>=2.2" "pyarrow>=17" "psycopg2-binary>=2.9"

ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/bing-pipeline/dags \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True \
    BING_SOURCE_FILE=/opt/bing-pipeline/data/BING_MultiDays.csv \
    BING_WORK_DIR=/opt/bing-pipeline/work
