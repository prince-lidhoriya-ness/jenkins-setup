
## YouTube Link
For the full 1 hour course watch on youtube:
https://www.youtube.com/watch?v=6YZvp2GwT0A

# Installation
## Build the Jenkins BlueOcean Docker Image (or pull and use the one I built)
```
docker build -t myjenkins-blueocean:2.516.3 .

#IF you are having problems building the image yourself, you can pull from my registry (It is version 2.332.3-1 though, the original from the video)

docker pull devopsjourney1/jenkins-blueocean:2.332.3-1 && docker tag devopsjourney1/jenkins-blueocean:2.332.3-1 myjenkins-blueocean:2.332.3-1
```

## Create the network 'jenkins'
```
docker network create jenkins
```

## Run the Docker daemon for Jenkins (docker:dind)
The `Quality Gates` stage runs its scanners with `docker compose` and bind-mounts the job workspace, so the daemon
must see `/var/jenkins_home` at the same path as Jenkins: it mounts the same `jenkins-data` volume.
Port 9000 publishes the SonarQube UI (http://localhost:9000) that the gates start inside this daemon.
```
docker run --name jenkins-docker --restart=unless-stopped --detach --privileged `
  --network jenkins --network-alias docker --env DOCKER_TLS_CERTDIR=/certs `
  --volume jenkins-docker-certs:/certs/client --volume jenkins-data:/var/jenkins_home `
  --volume jenkins-docker-data:/var/lib/docker `
  --publish 2376:2376 --publish 9000:9000 docker:dind --storage-driver overlay2
```
(MacOS / Linux: replace the trailing backticks with `\`.) Give Docker Desktop at least 6 GB RAM, since SonarQube needs about 4 GB.

Behind a TLS-inspecting proxy (Netskope etc.), image pulls inside dind fail with `x509: certificate signed by unknown authority`.
Fix: add `--env SSL_CERT_DIR=/corp-ca --volume C:\AI-office\jenkins-setup\jenkins-101\quality-gates\certs:/corp-ca:ro`
to the command above (the folder holding `corporate-ca.pem`).

## Run the Container
### MacOS / Linux
```
docker run --name jenkins-blueocean --restart=on-failure --detach \
  --network jenkins --env DOCKER_HOST=tcp://docker:2376 \
  --env DOCKER_CERT_PATH=/certs/client --env DOCKER_TLS_VERIFY=1 \
  --publish 8080:8080 --publish 50000:50000 \
  --volume jenkins-data:/var/jenkins_home \
  --volume jenkins-docker-certs:/certs/client:ro \
  myjenkins-blueocean:2.516.3
```

### Windows
```
docker run --name jenkins-blueocean --restart=on-failure --detach `
  --network jenkins --env DOCKER_HOST=tcp://docker:2376 `
  --env DOCKER_CERT_PATH=/certs/client --env DOCKER_TLS_VERIFY=1 `
  --volume jenkins-data:/var/jenkins_home `
  --volume jenkins-docker-certs:/certs/client:ro `
  --publish 8080:8080 --publish 50000:50000 myjenkins-blueocean:2.516.3
```


## Get the Password
```
docker exec jenkins-blueocean cat /var/jenkins_home/secrets/initialAdminPassword
```

## Connect to the Jenkins
```
https://localhost:8080/
```

## Installation Reference:
https://www.jenkins.io/doc/book/installing/docker/


## alpine/socat container to forward traffic from Jenkins to Docker Desktop on Host Machine

https://stackoverflow.com/questions/47709208/how-to-find-docker-host-uri-to-be-used-in-jenkins-docker-plugin
```
docker run -d --restart=always -p 127.0.0.1:2376:2375 --network jenkins -v /var/run/docker.sock:/var/run/docker.sock alpine/socat tcp-listen:2375,fork,reuseaddr unix-connect:/var/run/docker.sock
docker inspect <container_id> | grep IPAddress
```

## Using my Jenkins Python Agent
```
docker pull devopsjourney1/myjenkinsagents:python
```

# CI/CD with the quality gates
`Jenkinsfile` runs **Build -> Test -> Quality Gates -> Deliver**. The gates live in `quality-gates/` (details in
`quality-gates/README.md`, limits in `quality-gates/thresholds.yaml`). Deliver runs only when every gate passes.

| Gate | Checks |
|---|---|
| 1 | SonarQube, Semgrep (SAST), Trivy (vulnerable dependencies, Dockerfile misconfig) |
| 2 | Gitleaks secrets, hardcoded credentials, PII/PHI in code and logs |
| 3 | Claude spend / iteration budget (`results/cost_ledger.jsonl`) |
| 4 | HTTP evals (`evals/cases/*.yaml`) against the running app |

## One-time Jenkins setup
1. Rebuild the image (adds `docker-compose-plugin` and the missing `json-path-api`/`token-macro` plugins), then start `jenkins-docker` (above) and `jenkins-blueocean`.
2. *Manage Jenkins -> Nodes -> Built-In Node*: keep at least 1 executor. The `Quality Gates` stage runs there (label `built-in`) because it needs the docker CLI.
3. Behind a corporate proxy: *Manage Jenkins -> Credentials -> Add -> Secret file*, upload `quality-gates/certs/corporate-ca.pem`, and put its ID in the `CORPORATE_CA_CREDENTIAL` build parameter. The CA files are git-ignored, so the pipeline builds them from the system CAs plus this credential.
4. *New Item -> Pipeline* (or Multibranch Pipeline) -> *Pipeline script from SCM* -> Git -> your GitHub repo URL, script path `Jenkinsfile`.
   The first build only registers the parameters; run *Build with Parameters* after that.

## Build parameters
| Parameter | Default | Meaning |
|---|---|---|
| `GATE_PHASE` | `after` | `after` = enforced, build fails on a missed threshold. `before` = baseline, never fails |
| `GATES` | `1,2,3,4` | which gates to run |
| `SCAN_DIR` | `myapp` | folder the gates scan |
| `APP_COMPOSE_FILE` / `APP_COMPOSE_PROFILE` | empty | compose file that starts the app for gate 4. Empty = gate 4 skipped |
| `SKIP_SONARQUBE` | false | fast mode for quick tests |
| `CORPORATE_CA_CREDENTIAL` | empty | Secret-file credential ID of the corporate CA |

Run one `before` build first to record a baseline. Every later enforced build is then compared against it
(`results/comparison.md`). All results, including `feedback.md` with the failing thresholds and top findings, are archived as build artifacts.

Try the whole flow on the bundled sample app: `SCAN_DIR=quality-gates/samples/legacy-app`,
`APP_COMPOSE_FILE=quality-gates/samples/docker-compose.yml`, `APP_COMPOSE_PROFILE=legacy`, `GATE_PHASE=before`;
then `modernized-app` / `modernized` with `GATE_PHASE=after`.
