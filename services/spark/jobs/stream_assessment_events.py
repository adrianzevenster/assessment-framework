import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, from_json, sha2, to_timestamp
from pyspark.sql.types import StructField, StructType, StringType, IntegerType

BROKERS = os.getenv("REDPANDA_BROKERS", "localhost:19092")
WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3a://lakehouse/warehouse")

submission_schema = StructType([
    StructField("event_type", StringType()),
    StructField("event_time", StringType()),
    StructField("submission_id", StringType()),
    StructField("template_id", StringType()),
    StructField("respondent_id", StringType()),
    StructField("channel", StringType()),
    StructField("answer_count", IntegerType()),
])

response_schema = StructType([
    StructField("event_type", StringType()),
    StructField("event_time", StringType()),
    StructField("submission_id", StringType()),
    StructField("template_id", StringType()),
    StructField("respondent_id", StringType()),
    StructField("question_key", StringType()),
    StructField("answer_text", StringType()),
    StructField("answer_numeric", IntegerType()),
    StructField("answer_json", StringType()),
])

spark = (
    SparkSession.builder
    .appName("assessment-stream")
    .config("spark.sql.catalog.demo", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.demo.type", "hadoop")
    .config("spark.sql.catalog.demo.warehouse", WAREHOUSE)
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
    .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID", "minio"))
    .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY", "minio123"))
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .getOrCreate()
)

spark.sql("CREATE NAMESPACE IF NOT EXISTS demo.bronze")
spark.sql("CREATE NAMESPACE IF NOT EXISTS demo.silver")
spark.sql("CREATE NAMESPACE IF NOT EXISTS demo.gold")


def read_topic(topic: str):
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", BROKERS)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .load()
    )


submissions_raw = read_topic("assessment.submissions")
responses_raw = read_topic("assessment.responses")

bronze_submissions = submissions_raw.select(
    col("key").cast("string").alias("message_key"),
    col("value").cast("string").alias("raw_payload"),
    current_timestamp().alias("ingested_at"),
)

bronze_responses = responses_raw.select(
    col("key").cast("string").alias("message_key"),
    col("value").cast("string").alias("raw_payload"),
    current_timestamp().alias("ingested_at"),
)

silver_submissions = (
    submissions_raw
    .select(from_json(col("value").cast("string"), submission_schema).alias("d"))
    .select("d.*")
    .withColumn("event_time_ts", to_timestamp(col("event_time")))
    .withWatermark("event_time_ts", "1 hour")
    .dropDuplicates(["submission_id"])
    .withColumn("respondent_id", sha2(col("respondent_id"), 256))
)

silver_responses = (
    responses_raw
    .select(from_json(col("value").cast("string"), response_schema).alias("d"))
    .select("d.*")
    .withColumn("event_time_ts", to_timestamp(col("event_time")))
    .withWatermark("event_time_ts", "1 hour")
    .dropDuplicates(["submission_id", "question_key"])
    .withColumn("respondent_id", sha2(col("respondent_id"), 256))
)


def write_stream(df, table: str, checkpoint: str):
    return (
        df.writeStream
        .format("iceberg")
        .outputMode("append")
        .option("checkpointLocation", checkpoint)
        .toTable(table)
    )


write_stream(bronze_submissions, "demo.bronze.assessment_submissions_raw", "/tmp/checkpoints/bronze_submissions")
write_stream(bronze_responses, "demo.bronze.assessment_responses_raw", "/tmp/checkpoints/bronze_responses")
write_stream(silver_submissions, "demo.silver.fact_assessment_submission", "/tmp/checkpoints/silver_submissions")
write_stream(silver_responses, "demo.silver.fact_assessment_response", "/tmp/checkpoints/silver_responses")

spark.streams.awaitAnyTermination()
