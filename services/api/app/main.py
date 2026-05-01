from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.schemas import SubmissionCreate, TemplateCreate
from app.services import create_template, submit_assessment
from app.telemetry import configure_telemetry

app = FastAPI(title="Assessment Framework API", version="0.1.0")
Base.metadata.create_all(bind=engine)
configure_telemetry(app)


@app.get('/health')
def health():
    return {"status": "ok"}


@app.post('/templates')
def post_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    template = create_template(db, payload)
    return {"template_id": template.template_id, "status": template.status}


@app.post('/submissions')
def post_submission(payload: SubmissionCreate, db: Session = Depends(get_db)):
    submission = submit_assessment(db, payload)
    return {"submission_id": submission.submission_id, "status": submission.status}
