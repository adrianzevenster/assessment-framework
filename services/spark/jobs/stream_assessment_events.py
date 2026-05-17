import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, from_json
from pyspark.sql.types import StructField, StructType, StringType, IntegerType, MapType

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
    StructField("metadata", MapType(StringType(), StringType())),
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
    StructField("answer_json", MapType(StringType(), StringType())),
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

submissions_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", BROKERS)
    .option("subscribe", "assessment.submissions")
    .option("startingOffsets", "earliest")
    .load()
)

responses_raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", BROKERS)
    .option("subscribe", "assessment.responses")
    .option("startingOffsets", "earliest")
    .load()
)

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

silver_submissions = submissions_raw.select(from_json(col("value").cast("string"), submission_schema).alias("data")).select("data.*")
silver_responses = responses_raw.select(from_json(col("value").cast("string"), response_schema).alias("data")).select("data.*")

bronze_submissions.writeStream     .format("iceberg")     .outputMode("append")     .option("checkpointLocation", "/tmp/checkpoints/bronze_submissions")     .toTable("demo.bronze.assessment_submissions_raw")

bronze_responses.writeStream.format("iceberg")     .outputMode("append")     .option("checkpointLocation", "/tmp/checkpoints/bronze_responses")     .toTable("demo.bronze.assessment_responses_raw")

silver_submissions.writeStream     .format("iceberg")     .outputMode("append")     .option("checkpointLocation", "/tmp/checkpoints/silver_submissions")     .toTable("demo.silver.fact_assessment_submission")

query = silver_responses.writeStream     .format("iceberg")     .outputMode("append")     .option("checkpointLocation", "/tmp/checkpoints/silver_responses")     .toTable("demo.silver.fact_assessment_response")

query.awaitTermination()
