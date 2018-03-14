PYTHON ?= python
ifeq ($(origin VIRTUAL_ENV),undefined)
	DIST_PYTHON ?= pipenv run $(PYTHON)
else
	DIST_PYTHON ?= $(PYTHON)
endif
IMAGE_NAME ?= ansible-runner

.PHONY: dist dev shell image devimage

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

dev:
	pipenv install

shell:
	pipenv shell

image:
	docker pull centos:7
	docker build --rm=true -t $(IMAGE_NAME) .

devimage:
	docker build --rm=true -t $(IMAGE_NAME)-dev -f Dockerfile.dev .
