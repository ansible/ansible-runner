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
    RELEASE ?= 0.git$(shell date -u +%Y%m%d%H%M)_$(shell git rev-parse --short HEAD)
endif

# RPM build variables
MOCK_BIN ?= mock
MOCK_CONFIG ?= epel-7-x86_64

RPM_NVR = $(NAME)-$(VERSION)-$(RELEASE)$(RPM_DIST)
RPM_DIST ?= $(shell rpm --eval '%{?dist}' 2>/dev/null)
RPM_ARCH ?= $(shell rpm --eval '%{_arch}' 2>/dev/null)

# Provide a fallback value for RPM_ARCH
ifeq ($(RPM_ARCH),)
    RPM_ARCH = $(shell uname -m)
endif

# DEB build variables
DEB_DIST ?=
DEB_ARCH ?= amd64
DEB_NVR = $(NAME)_$(VERSION)-$(RELEASE)~$(DEB_DIST)
DEB_NVRA = $(DEB_NVR)_$(DEB_ARCH)
DEB_TAR_NAME=$(NAME)-$(VERSION)
DEB_TAR_FILE=$(NAME)_$(VERSION).orig.tar.gz
DEBUILD_BIN ?= debuild
DEBUILD_OPTS ?= -us -uc
DEBUILD = $(DEBUILD_BIN) $(DEBUILD_OPTS)


.PHONY: clean dist sdist dev shell image devimage rpm srpm docs

clean:
	rm -rf dist
	rm -rf rpm-build
	rm -rf deb-build

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

sdist: dist/$(PIP_NAME)-$(VERSION).tar.gz

dist/$(PIP_NAME)-$(VERSION).tar.gz:
	$(DIST_PYTHON) setup.py sdist

dev:
	pipenv install

shell:
	pipenv shell

test:
	tox

docs:
	cd docs && make html

image:
	docker pull centos:7
	docker build --rm=true -t $(IMAGE_NAME) .

devimage:
	docker pull centos:7
	docker build --rm=true -t $(IMAGE_NAME)-dev -f Dockerfile.dev .

rpm:
	docker-compose -f packaging/rpm/docker-compose.yml \
	  run --rm -e RELEASE=$(RELEASE) rpm-builder "make mock-rpm"

srpm:
	docker-compose -f packaging/rpm/docker-compose.yml \
	  run --rm -e RELEASE=$(RELEASE) rpm-builder "make mock-srpm"

mock-rpm: rpm-build/$(RPM_NVR).$(RPM_ARCH).rpm

rpm-build/$(RPM_NVR).$(RPM_ARCH).rpm: rpm-build/$(RPM_NVR).src.rpm
	$(MOCK_BIN) -r $(MOCK_CONFIG) --arch=noarch \
	  --resultdir=rpm-build \
	  --rebuild rpm-build/$(RPM_NVR).src.rpm

mock-srpm: rpm-build/$(RPM_NVR).src.rpm

rpm-build/$(RPM_NVR).src.rpm: dist/$(PIP_NAME)-$(VERSION).tar.gz rpm-build rpm-build/$(NAME).spec
	$(MOCK_BIN) -r $(MOCK_CONFIG) --arch=noarch \
	  --resultdir=rpm-build \
	  --spec=rpm-build/$(NAME).spec \
	  --sources=rpm-build \
	  --buildsrpm

rpm-build/$(NAME).spec:
	ansible -c local -i localhost, all \
	    -m template \
	    -a "src=packaging/rpm/$(NAME).spec.j2 dest=rpm-build/$(NAME).spec" \
	    -e version=$(VERSION) \
	    -e release=$(RELEASE)

rpm-build: sdist
	mkdir -p $@
	cp dist/$(NAME)-$(VERSION).tar.gz rpm-build/$(NAME)-$(VERSION)-$(RELEASE).tar.gz

deb:
	docker-compose -f packaging/debian/docker/docker-compose.yml \
          run --rm deb-builder "make mock-deb"

mock-deb: deb-build/$(DEB_NVRA).deb

deb-build/$(DEB_NVRA).deb: deb-build
	cd deb-build && tar -xf $(NAME)_$(VERSION).orig.tar.gz
	cp -a packaging/debian deb-build/$(DEB_TAR_NAME)/
	cd deb-build/$(DEB_TAR_NAME) && $(DEBUILD)
	rm -rf deb-build/$(DEB_TAR_NAME)

deb-build: sdist
	mkdir -p $@
	cp dist/$(NAME)-$(VERSION).tar.gz deb-build/$(NAME)_$(VERSION).orig.tar.gz
