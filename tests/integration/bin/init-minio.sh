#!/bin/bash
# Script to initialize MinIO for testing

# Wait for MinIO to be ready
echo "Waiting for MinIO to start..."
while ! curl -s http://minio:9000/minio/health/ready; do
  echo "MinIO not ready yet, waiting..."
  sleep 1
done

echo "MinIO is ready!"

# Create a test bucket using MinIO client
mc alias set myminio http://minio:9000 minioadmin minioadmin
mc mb myminio/runpod-images

# Configure bucket policy to allow uploads
cat > /tmp/policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::runpod-images"]
    },
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::runpod-images/*"]
    }
  ]
}
EOF

mc policy set /tmp/policy.json myminio/runpod-images

echo "Test bucket 'runpod-images' created and configured successfully" 