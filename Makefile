PYTHON ?= python
ifeq ($(origin VIRTUAL_ENV), undefined)
    DIST_PYTHON ?= pipenv run $(PYTHON)
else
    DIST_PYTHON ?= $(PYTHON)
endif

NAME = ansible-runner
IMAGE_NAME ?= $(NAME)
PIP_NAME = ansible_runner
VERSION := $(shell $(DIST_PYTHON) setup.py --version)
ifeq ($(OFFICIAL),yes)
    RELEASE ?= 1
else
    ifeq ($(origin RELEASE), undefined)
        RELEASE := 0.git$(shell date -u +%Y%m%d%H).$(shell git rev-parse --short HEAD)
    endif
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

# Debian Packaging
DEBUILD_BIN ?= debuild
DEBUILD_OPTS ?=
DPUT_BIN ?= dput
DPUT_OPTS ?=
DEB_DIST ?= xenial

GPG_KEY_ID ?=

ifeq ($(origin GPG_SIGNING_KEY), undefined)
    GPG_SIGNING_KEY = /dev/null
endif

ifeq ($(OFFICIAL),yes)
    # Sign official builds
    DEBUILD_OPTS += -k$(GPG_KEY_ID)
else
    # Do not sign unofficial builds
    DEBUILD_OPTS += -uc -us
endif

DEBUILD = $(DEBUILD_BIN) $(DEBUILD_OPTS)
DEB_PPA ?= mini_dinstall
DEB_ARCH ?= amd64
DEB_NVR = $(NAME)_$(VERSION)-$(RELEASE)~$(DEB_DIST)
DEB_NVRA = $(DEB_NVR)_$(DEB_ARCH)
DEB_NVRS = $(DEB_NVR)_source
DEB_TAR_NAME=$(NAME)-$(VERSION)
DEB_TAR_FILE=$(NAME)_$(VERSION).orig.tar.gz
DEB_DATE := $(shell LC_TIME=C date +"%a, %d %b %Y %T %z")

.PHONY: clean dist sdist dev shell image devimage rpm srpm docs deb debian deb-src

clean:
	rm -rf dist
	rm -rf build
	rm -rf ansible-runner.egg-info
	rm -rf rpm-build
	rm -rf deb-build
	find . -type f -regex ".*\py[co]$$" -delete

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

sdist: dist/$(NAME)-$(VERSION).tar.gz

dist/$(NAME)-$(VERSION).tar.gz:
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
	docker pull centos:8
	docker build --rm=true -t $(IMAGE_NAME) .

devimage:
	docker pull centos:8
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

rpm-build/$(RPM_NVR).src.rpm: dist/$(NAME)-$(VERSION).tar.gz rpm-build rpm-build/$(NAME).spec
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
		run --rm \
		-e OFFICIAL=$(OFFICIAL) -e DEB_DIST=$(DEB_DIST) -e RELEASE=$(RELEASE) \
		-e GPG_KEY_ID=$(GPG_KEY_ID) -e GPG_SIGNING_KEY=$(GPG_SIGNING_KEY) \
		deb-builder "make debian"

ifeq ($(OFFICIAL),yes)
debian: gpg-import deb-build/$(DEB_NVRA).deb
gpg-import:
	gpg --import /signing_key.asc
else
debian: deb-build/$(DEB_NVRA).deb
endif

deb-src: deb-build/$(DEB_NVR).dsc

deb-build/$(DEB_NVRA).deb: deb-build/$(DEB_NVR).dsc
	cd deb-build/$(NAME)-$(VERSION) && $(DEBUILD) -b

deb-build/$(DEB_NVR).dsc: deb-build/$(NAME)-$(VERSION)
	cd deb-build/$(NAME)-$(VERSION) && $(DEBUILD) -S

deb-build/$(NAME)-$(VERSION): dist/$(NAME)-$(VERSION).tar.gz
	mkdir -p $(dir $@)
	@if [ "$(OFFICIAL)" != "yes" ] ; then \
	  tar -C deb-build/ -xvf dist/$(NAME)-$(VERSION).tar.gz ; \
	  cd deb-build && tar czf $(DEB_TAR_FILE) $(NAME)-$(VERSION) ; \
	else \
	  cp -a dist/$(NAME)-$(VERSION).tar.gz deb-build/$(DEB_TAR_FILE) ; \
	fi
	cd deb-build && tar -xf $(DEB_TAR_FILE)
	cp -a packaging/debian deb-build/$(NAME)-$(VERSION)/
	sed -ie "s|%VERSION%|$(VERSION)|g;s|%RELEASE%|$(RELEASE)|;s|%DEB_DIST%|$(DEB_DIST)|g;s|%DATE%|$(DEB_DATE)|g" $@/debian/changelog

print-%:
	@echo $($*)
