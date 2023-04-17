# This is not fully compatible builder Dockerfile, but meets the needs of tests
FROM quay.io/centos/centos:stream9
ARG WHEEL
COPY $WHEEL /$WHEEL
RUN dnf install -y python3-pip
RUN python3 -m pip install /$WHEEL ansible-core
RUN mkdir -p /runner/{env,inventory,project,artifacts} /home/runner/.ansible/tmp
RUN chmod -R 777 /runner /home/runner
WORKDIR /runner
ENV HOME=/home/runner
CMD ["ansible-runner", "run", "/runner"]
