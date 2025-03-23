gcloud artifacts repositories add-iam-policy-binding gcr.io \
    --location=us \
    --member="allUsers" \
    --role="roles/artifactregistry.reader" \
    --project=PROJECT_ID

