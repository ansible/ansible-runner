PYTHON ?= python
IMAGE_NAME ?= ansible-runner

.PHONY: dist
dist:
	$(PYTHON) setup.py bdist_wheel --universal

.PHONY: dev
dev:
	pipenv install

.PHONY: shell
shell:
	pipenv shell

.PHONY: image
image:
	docker build --rm=true -t $(IMAGE_NAME) .
