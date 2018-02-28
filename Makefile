PYTHON ?= python
IMAGE_NAME ?= ansible-runner

.PHONY: dist dev shell image devimage

dist:
	$(PYTHON) setup.py bdist_wheel --universal

dev:
	pipenv install

shell:
	pipenv shell

image:
	docker build --rm=true -t $(IMAGE_NAME) .

devimage:
	docker build --rm=true -t $(IMAGE_NAME)-dev -f Dockerfile.dev .
