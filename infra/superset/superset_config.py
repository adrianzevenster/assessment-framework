SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://assessment:assessment@postgres:5432/superset"
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True}
TALISMAN_ENABLED = False
TALISMAN_CONFIG = {
    "force_https": False,
    "force_https_permanent": False,
    "frame_options": "ALLOWALL",
    "content_security_policy": None,
}
HTTP_HEADERS = {}
WTF_CSRF_ENABLED = False
