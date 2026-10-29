FROM jenkins/jenkins:2.516.3-jdk17
USER root
RUN apt-get update && apt-get install -y lsb-release python3-pip
RUN curl -fsSLo /usr/share/keyrings/docker-archive-keyring.asc \
  https://download.docker.com/linux/debian/gpg
RUN echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/usr/share/keyrings/docker-archive-keyring.asc] \
  https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
# docker-compose-plugin: the quality gates (quality-gates/run_gates.sh) run every scanner via `docker compose`
RUN apt-get update && apt-get install -y docker-ce-cli docker-compose-plugin
USER jenkins
# token-macro / json-path-api / github are listed explicitly: missing json-path-api broke token-macro,
# which took down the github plugin and Blue Ocean on startup
RUN jenkins-plugin-cli --plugins blueocean docker-workflow json-path-api token-macro \
  git github github-branch-source workflow-aggregator
