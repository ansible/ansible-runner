PYTHON ?= python
ifeq ($(origin VIRTUAL_ENV),undefined)
	DIST_PYTHON ?= pipenv run $(PYTHON)
else
	DIST_PYTHON ?= $(PYTHON)
endif

NAME = ansible-runner
IMAGE_NAME ?= $(NAME)
PIP_NAME = ansible_runner
VERSION = $(shell $(DIST_PYTHON) setup.py --version)
ifeq ($(OFFICIAL),yes)
    RELEASE ?= 1
else
    RELEASE ?= 0
endif

.PHONY: dist dev shell image devimage rpm sdist clean

clean:
	rm -rf dist
	rm -rf rpm-build

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

sdist: dist/$(PIP_NAME)-$(VERSION).tar.gz

dist/$(PIP_NAME)-$(VERSION).tar.gz:
	$(DIST_PYTHON) setup.py sdist

dev:
	pipenv install

shell:
	pipenv shell

image:
	docker pull centos:7
	docker build --rm=true -t $(IMAGE_NAME) .

devimage:
	docker pull centos:7
	docker build --rm=true -t $(IMAGE_NAME)-dev -f Dockerfile.dev .

# RPM Builds
MOCK_BIN ?= mock

RPM_NVR = $(NAME)-$(VERSION)-$(RELEASE)$(RPM_DIST)
RPM_DIST ?= $(shell rpm --eval '%{?dist}' 2>/dev/null)
RPM_ARCH ?= $(shell rpm --eval '%{_arch}' 2>/dev/null)

# Provide a fallback value for RPM_ARCH
ifeq ($(RPM_ARCH),)
    RPM_ARCH = $(shell uname -m)
endif

rpm:
	docker-compose -f packaging/rpm/docker-compose.yml \
	  run --rm rpm-builder "make mock-rpm"

mock-rpm: rpm-build/$(RPM_NVR).$(RPM_ARCH).rpm

rpm-build/$(RPM_NVR).$(RPM_ARCH).rpm: rpm-build/$(RPM_NVR).src.rpm
	$(MOCK_BIN) -r epel-7-x86_64 \
	  --resultdir=rpm-build \
	  --rebuild rpm-build/$(RPM_NVR).src.rpm

mock-srpm: rpm-build/$(RPM_NVR).src.rpm

rpm-build/$(RPM_NVR).src.rpm: dist/$(PIP_NAME)-$(VERSION).tar.gz rpm-build
	$(MOCK_BIN) -r epel-7-x86_64 \
	  --resultdir=rpm-build \
	  --spec=packaging/rpm/$(NAME).spec \
	  --sources=dist \
	  --buildsrpm

rpm-build:
	mkdir -p $@
