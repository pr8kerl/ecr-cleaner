FROM python:2.7.12-alpine

ENV TERRAFORM_VERSION=0.9.2
RUN apk --update add bash curl unzip zip && \
  mkdir -p /opt/terraform && \
  curl -L -o /opt/terraform/terraform.zip https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
  unzip /opt/terraform/terraform.zip -d /opt/terraform/ && \
  ln -s /opt/terraform/terraform /usr/local/bin/terraform && \
  rm -rf /opt/terraform/terraform.zip /var/cache/apk/*

RUN pip install --upgrade pip && pip install awscli

WORKDIR /app
ENV PYTHONPATH $PYTHONPATH:/app
