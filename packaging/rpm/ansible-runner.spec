%global pip_name ansible_runner

Name: ansible-runner
Version: 1.0
Release: 0%{?dist}
Summary: Package for interfacing with Ansible
Source0: https://github.com/ansible/%{name}/archive/%{version}.tar.gz?/%{pip_name}-%{version}.tar.gz

Group: Development/Libraries
License: ASL 2.0
Url: http://ansible.com

BuildRequires: python-setuptools

Requires: ansible
Requires: bubblewrap
Requires: bzip2
Requires: openssh
Requires: openssh-clients
Requires: python-crypto
Requires: python-daemon
Requires: python-memcached
Requires: python-pexpect
Requires: python-psutil

%description
A CLI and Python library that helps interfacing with Ansible from other systems

%prep
%setup -q -n %{pip_name}-%{version}

%build
# Disable debuginfo packages
%define _enable_debug_package 0
%define debug_package %{nil}

%{__python} setup.py build

%install
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

%files
%{_bindir}/ansible-runner
%{python_sitelib}/*
