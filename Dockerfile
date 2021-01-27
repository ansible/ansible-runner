ARG ANSIBLE_CORE_IMAGE=quay.io/ansible/ansible-core:latest

FROM quay.io/ansible/python-builder:latest as builder
# =============================================================================

ARG ANSIBLE_BRANCH=""
ARG ZUUL_SIBLINGS=""
COPY . /tmp/src
RUN if [ "$ANSIBLE_BRANCH" != "" ] ; then \
      echo "Installing requirements.txt / upper-constraints.txt for Ansible $ANSIBLE_BRANCH" ; \
      cp /tmp/src/tools/bindep-$ANSIBLE_BRANCH.txt /tmp/src/bindep.txt ; \
      cp /tmp/src/tools/requirements-$ANSIBLE_BRANCH.txt /tmp/src/requirements.txt ; \
      cp /tmp/src/tools/upper-constraints-$ANSIBLE_BRANCH.txt /tmp/src/upper-constraints.txt ; \
    fi
RUN assemble

FROM $ANSIBLE_CORE_IMAGE as ansible-core
# =============================================================================

COPY --from=builder /output/ /output
RUN /output/install-from-bindep \
  && rm -rf /output

# Prepare the /runner folder, seed the folder with demo data
ADD demo /runner

# In OpenShift, container will run as a random uid number and gid 0. Make sure things
# are writeable by the root group.
RUN for dir in \
      /home/runner \
      /home/runner/.ansible \
      /home/runner/.ansible/tmp \
      /runner \
      /home/runner \
      /runner/env \
      /runner/inventory \
      /runner/project \
      /runner/artifacts ; \
    do mkdir -m 0775 -p $dir ; chmod -R g+rwx $dir ; chgrp -R root $dir ; done && \
    for file in \
      /home/runner/.ansible/galaxy_token \
      /etc/passwd \
      /etc/group ; \
    do touch $file ; chmod g+rw $file ; chgrp root $file ; done

VOLUME /runner

WORKDIR /runner

ENV HOME=/home/runner

ADD utils/entrypoint.sh /bin/entrypoint
RUN chmod +x /bin/entrypoint

ENTRYPOINT ["entrypoint"]
CMD ["ansible-runner", "run", "/runner"]
